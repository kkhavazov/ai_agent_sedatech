import json
import sqlite3

import pytest

import database


@pytest.fixture
def cache_path(tmp_path, monkeypatch):
    path = tmp_path / "cache.db"
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    return path


def test_migration_preserves_but_does_not_serve_old_drafts(cache_path):
    with sqlite3.connect(cache_path) as connection:
        connection.execute("""
            CREATE TABLE drafts (
                ticket_id TEXT NOT NULL,
                based_on_message_id TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (ticket_id, based_on_message_id)
            )
        """)
        connection.execute(
            "INSERT INTO drafts VALUES (?, ?, ?, ?)",
            ("ticket-1", "message-1", json.dumps({"reply": "Hello"}), "2026-09-18"),
        )

    database.initialize_database()
    database.initialize_database()

    assert database.get_cached_draft("ticket-1", "message-1") is None
    with sqlite3.connect(cache_path) as connection:
        assert connection.execute("SELECT count(*) FROM drafts").fetchone()[0] == 1

    replacement = {"reply": "Bonjour", "sources": []}
    database.store_draft("ticket-1", "message-1", replacement)
    assert database.get_cached_draft("ticket-1", "message-1") == replacement


@pytest.mark.parametrize("draft", [{"reply": "Bonjour", "sources": []}, "Bonjour, voici la révision."])
def test_current_generated_and_revised_drafts_are_cached(cache_path, draft):
    database.initialize_database()
    database.store_draft("ticket-1", "message-1", draft)

    assert database.get_cached_draft("ticket-1", "message-1") == draft
    assert database.get_cached_draft("ticket-2", "message-1") is None
    assert database.get_cached_draft("ticket-1", "message-2") is None


def test_policy_change_invalidates_cached_draft(cache_path, monkeypatch):
    database.initialize_database()
    database.store_draft("ticket-1", "message-1", {"reply": "Bonjour"})

    monkeypatch.setattr(database, "TICKET_REPLY_PROMPT_VERSION", "updated-policy")
    assert database.get_cached_draft("ticket-1", "message-1") is None
