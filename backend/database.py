import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from prompts import TICKET_REPLY_PROMPT_VERSION


DATABASE_PATH = Path(
    os.getenv("CACHE_DATABASE_PATH", Path(__file__).with_name("cache.db"))
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _read_connection():
    """Return a raw connection suitable for read-only queries.

    The caller is responsible for closing the returned connection.
    Used by read helpers so commits do not leak into unrelated functions.
    """
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_database() -> None:
    with _connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                last_message_id TEXT NOT NULL,
                message_ids_json TEXT NOT NULL,
                synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                role TEXT NOT NULL,
                body TEXT NOT NULL,
                position INTEGER NOT NULL,
                visible INTEGER NOT NULL DEFAULT 1,
                cached_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_ticket_position
            ON messages(ticket_id, position);

            CREATE TABLE IF NOT EXISTS drafts (
                ticket_id TEXT NOT NULL,
                based_on_message_id TEXT NOT NULL,
                response_json TEXT NOT NULL,
                prompt_version TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (ticket_id, based_on_message_id)
            );

            CREATE TABLE IF NOT EXISTS translations (
                cache_key TEXT PRIMARY KEY,
                translated_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generation_logs (
                ticket_id TEXT NOT NULL,
                based_on_message_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK(event_type IN ('first_draft', 'reprompt')),
                response_text TEXT NOT NULL DEFAULT '',
                sources_json TEXT NOT NULL DEFAULT '[]',
                instructions TEXT NOT NULL DEFAULT '',
                message_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (ticket_id, based_on_message_id, event_type)
            );

            CREATE INDEX IF NOT EXISTS idx_generation_logs_ticket
            ON generation_logs(ticket_id, event_type);

            CREATE INDEX IF NOT EXISTS idx_generation_logs_created
            ON generation_logs(created_at);
            """
        )
        # Rebuild the old composite-key table without losing existing events.
        connection.execute("BEGIN IMMEDIATE")
        log_columns = {row["name"] for row in connection.execute(
            "PRAGMA table_info(generation_logs)"
        )}
        if "id" not in log_columns:
            connection.execute("ALTER TABLE generation_logs RENAME TO generation_logs_legacy")
            connection.execute("""
                CREATE TABLE generation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL,
                    based_on_message_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('first_draft', 'reprompt')),
                    response_text TEXT NOT NULL DEFAULT '',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    instructions TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    messages_json TEXT,
                    input_response_text TEXT,
                    first_draft_id INTEGER REFERENCES generation_logs(id),
                    prompt_version TEXT NOT NULL DEFAULT ''
                )
            """)
            connection.execute("""
                INSERT INTO generation_logs (
                    ticket_id, based_on_message_id, event_type, response_text,
                    sources_json, instructions, message_count, created_at
                ) SELECT ticket_id, based_on_message_id, event_type, response_text,
                    sources_json, instructions, message_count, created_at
                FROM generation_logs_legacy ORDER BY created_at
            """)
            connection.execute("DROP TABLE generation_logs_legacy")
            connection.execute("""
                UPDATE generation_logs SET first_draft_id = (
                    SELECT original.id FROM generation_logs AS original
                    WHERE original.ticket_id = generation_logs.ticket_id
                      AND original.based_on_message_id = generation_logs.based_on_message_id
                      AND original.event_type = 'first_draft'
                ) WHERE event_type = 'reprompt'
            """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_generation_logs_ticket ON generation_logs(ticket_id, event_type)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_generation_logs_created ON generation_logs(created_at)")
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_generation_logs_first
            ON generation_logs(ticket_id, based_on_message_id)
            WHERE event_type = 'first_draft'
        """)
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "visible" not in columns:
            connection.execute(
                "ALTER TABLE messages ADD COLUMN visible INTEGER NOT NULL DEFAULT 1"
            )
        draft_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(drafts)").fetchall()
        }
        if "prompt_version" not in draft_columns:
            connection.execute(
                "ALTER TABLE drafts ADD COLUMN prompt_version TEXT NOT NULL DEFAULT ''"
            )


def get_ticket_revision(ticket_id: str) -> str | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT last_message_id FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
    return row["last_message_id"] if row else None


def get_cached_messages(ticket_id: str, message_ids: list[str]) -> list[dict] | None:
    if not message_ids:
        return []

    placeholders = ",".join("?" for _ in message_ids)
    with _connection() as connection:
        rows = connection.execute(
            f"""
            SELECT message_id, role, body, visible
            FROM messages
            WHERE ticket_id = ? AND message_id IN ({placeholders})
            """,
            (ticket_id, *message_ids),
        ).fetchall()

    by_id = {row["message_id"]: row for row in rows}
    if any(message_id not in by_id for message_id in message_ids):
        return None
    return [
        {"role": by_id[message_id]["role"], "text": by_id[message_id]["body"]}
        for message_id in message_ids
        if by_id[message_id]["visible"]
    ]


def get_cached_message_ids(ticket_id: str, message_ids: list[str]) -> set[str]:
    if not message_ids:
        return set()
    placeholders = ",".join("?" for _ in message_ids)
    with _connection() as connection:
        rows = connection.execute(
            f"""
            SELECT message_id FROM messages
            WHERE ticket_id = ? AND message_id IN ({placeholders})
            """,
            (ticket_id, *message_ids),
        ).fetchall()
    return {row["message_id"] for row in rows}


def store_ticket_messages(
    ticket_id: str,
    message_ids: list[str],
    messages_by_id: dict[str, dict],
) -> None:
    if not message_ids:
        return

    now = _now()
    with _connection() as connection:
        for position, message_id in enumerate(message_ids):
            message = messages_by_id.get(message_id)
            if message is None:
                continue
            connection.execute(
                """
                INSERT INTO messages (
                    message_id, ticket_id, role, body, position, visible, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    ticket_id = excluded.ticket_id,
                    role = excluded.role,
                    body = excluded.body,
                    position = excluded.position,
                    visible = excluded.visible,
                    cached_at = excluded.cached_at
                """,
                (
                    message_id,
                    ticket_id,
                    message["role"],
                    message["text"] or "",
                    position,
                    int(message.get("visible", True)),
                    now,
                ),
            )

        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, last_message_id, message_ids_json, synced_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET
                last_message_id = excluded.last_message_id,
                message_ids_json = excluded.message_ids_json,
                synced_at = excluded.synced_at
            """,
            (ticket_id, message_ids[-1], json.dumps(message_ids), now),
        )


def get_cached_draft(ticket_id: str, last_message_id: str) -> dict | str | None:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT response_json FROM drafts
            WHERE ticket_id = ? AND based_on_message_id = ?
                AND prompt_version = ?
            """,
            (ticket_id, last_message_id, TICKET_REPLY_PROMPT_VERSION),
        ).fetchone()
    return json.loads(row["response_json"]) if row else None


def store_draft(
    ticket_id: str, last_message_id: str, response: dict | str, *,
    event_type: Literal["first_draft", "reprompt"] | None = None,
    messages: list[dict] | None = None,
    instructions: str | None = None,
    input_response: str | None = None,
) -> None:
    """Save the cache and optional generation event in one transaction."""
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO drafts (
                ticket_id, based_on_message_id, response_json, created_at, prompt_version
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id, based_on_message_id) DO UPDATE SET
                response_json = excluded.response_json,
                created_at = excluded.created_at,
                prompt_version = excluded.prompt_version
            """,
            (ticket_id, last_message_id, json.dumps(response), _now(), TICKET_REPLY_PROMPT_VERSION),
        )
        if event_type is not None:
            _insert_generation_log(
                connection, ticket_id, last_message_id, event_type=event_type,
                reply=response.get("reply", "") if isinstance(response, dict) else response,
                sources=response.get("sources") if isinstance(response, dict) else None,
                instructions=instructions, messages=messages,
                message_count=len(messages or []), input_response=input_response,
            )



# ---------------------------------------------------------------------------
# Generation logs — capture initial draft + revision history for model loops
# ---------------------------------------------------------------------------

def _insert_generation_log(
    connection, ticket_id, based_on_message_id, *, event_type,
    reply="", sources=None, instructions=None, message_count=0,
    messages=None, input_response=None,
):
    connection.execute(
        """
        INSERT INTO generation_logs (
            ticket_id, based_on_message_id, event_type, response_text,
            sources_json, instructions, message_count, created_at,
            messages_json, input_response_text, first_draft_id, prompt_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (
            SELECT id FROM generation_logs
            WHERE ticket_id = ? AND based_on_message_id = ? AND event_type = 'first_draft'
        ), ?)
        ON CONFLICT(ticket_id, based_on_message_id) WHERE event_type = 'first_draft'
        DO NOTHING
        """,
        (ticket_id, based_on_message_id, event_type, reply, json.dumps(sources or []),
         instructions or "", message_count, _now(),
         json.dumps(messages, ensure_ascii=False) if messages is not None else None,
         input_response, ticket_id, based_on_message_id, TICKET_REPLY_PROMPT_VERSION),
    )


def store_generation_log(
    ticket_id: str, based_on_message_id: str, *,
    event_type: Literal["first_draft", "reprompt"], reply: str = "",
    sources: list[str] | None = None, instructions: str | None = None,
    message_count: int = 0, messages: list[dict] | None = None,
    input_response: str | None = None,
) -> None:
    """Append a revision event; preserve the first draft for each ticket revision."""
    with _connection() as connection:
        _insert_generation_log(
            connection, ticket_id, based_on_message_id, event_type=event_type,
            reply=reply, sources=sources, instructions=instructions,
            message_count=len(messages) if messages is not None else message_count,
            messages=messages, input_response=input_response,
        )


def get_generation_logs(
    ticket_id: str | None = None,
) -> list[dict]:
    """Return generation logs, optionally filtered by ticket."""
    conn = _read_connection()
    try:
        if ticket_id is not None:
            rows = conn.execute(
                "SELECT * FROM generation_logs WHERE ticket_id = ? ORDER BY created_at, id",
                (ticket_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM generation_logs ORDER BY created_at DESC, id DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_first_draft_for_ticket(ticket_id: str) -> dict | None:
    """Retrieve the first-draft log entry (if any) for a ticket."""
    conn = _read_connection()
    try:
        row = conn.execute(
            "SELECT * FROM generation_logs WHERE ticket_id = ? AND event_type = 'first_draft' ORDER BY created_at LIMIT 1",
            (ticket_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_sources_for_ticket(ticket_id: str, last_message_id: str) -> list[str]:
    """Return original retrieval sources; reprompts do not run a new search."""
    draft = get_cached_draft(ticket_id, last_message_id)
    if isinstance(draft, dict) and "sources" in draft:
        return draft["sources"] or []
    conn = _read_connection()
    try:
        row = conn.execute(
            "SELECT sources_json FROM generation_logs "
            "WHERE ticket_id = ? AND based_on_message_id = ? "
            "AND event_type = 'first_draft' "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (ticket_id, last_message_id),
        ).fetchone()
        if row and row["sources_json"]:
            return json.loads(row["sources_json"])
        return []
    finally:
        conn.close()


def get_cached_translation(cache_key: str) -> str | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT translated_text FROM translations WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    return row["translated_text"] if row else None


def store_translation(cache_key: str, translated_text: str) -> None:
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO translations (cache_key, translated_text, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                translated_text = excluded.translated_text,
                created_at = excluded.created_at
            """,
            (cache_key, translated_text, _now()),
        )
