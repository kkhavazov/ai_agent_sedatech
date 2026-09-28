import json
import sqlite3

import pytest

import database


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "cache.db")
    database.initialize_database()


def test_multiple_reprompts_preserve_original_and_snapshots(cache):
    messages = [{"role": "Customer", "text": "My PC is broken"}]
    database.store_draft("t1", "m1", {"reply": "Original", "sources": ["s1"]},
                         event_type="first_draft", messages=messages)
    for before, instruction, after in [("Original", "Shorter", "Short"),
                                        ("Short", "More formal", "Formal")]:
        database.store_draft("t1", "m1", after, event_type="reprompt",
                             messages=messages, instructions=instruction, input_response=before)
    logs = database.get_generation_logs("t1")
    assert [row["response_text"] for row in logs] == ["Original", "Short", "Formal"]
    assert [row["instructions"] for row in logs] == ["", "Shorter", "More formal"]
    assert [row["input_response_text"] for row in logs] == [None, "Original", "Short"]
    assert all(row["first_draft_id"] == logs[0]["id"] for row in logs[1:])
    assert all(json.loads(row["messages_json"]) == messages for row in logs)
    assert database.get_cached_draft("t1", "m1") == "Formal"
    database.store_generation_log("t1", "m1", event_type="first_draft", reply="Replacement")
    assert database.get_first_draft_for_ticket("t1")["response_text"] == "Original"
    database.store_draft("t1", "m2", "New context", event_type="first_draft", messages=[])
    database.store_draft("t1", "m2", "New revision", event_type="reprompt", messages=[])
    logs = database.get_generation_logs("t1")
    assert logs[-1]["first_draft_id"] == logs[-2]["id"]


def test_failed_log_rolls_back_cached_draft(cache):
    database.store_draft("t1", "m1", "Original")
    with pytest.raises(sqlite3.IntegrityError):
        database.store_draft("t1", "m1", "Replacement", event_type="invalid")
    assert database.get_cached_draft("t1", "m1") == "Original"
    assert database.get_generation_logs("t1") == []


def test_legacy_logs_migrate_without_losing_events(monkeypatch, tmp_path):
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE generation_logs (
                ticket_id TEXT, based_on_message_id TEXT, event_type TEXT,
                response_text TEXT, sources_json TEXT, instructions TEXT,
                message_count INTEGER, created_at TEXT,
                PRIMARY KEY(ticket_id, based_on_message_id, event_type)
            );
            INSERT INTO generation_logs VALUES ('t1', 'm1', 'first_draft', 'Original', '[]', '', 1, '2026-01-01');
            INSERT INTO generation_logs VALUES ('t1', 'm1', 'reprompt', 'Revised', '[]', 'Shorter', 1, '2026-01-02');
        """)
    database.initialize_database()
    database.initialize_database()
    database.store_generation_log("t1", "m1", event_type="reprompt", reply="Third")
    logs = database.get_generation_logs("t1")
    assert [row["response_text"] for row in logs] == ["Original", "Revised", "Third"]
    assert logs[1]["first_draft_id"] == logs[0]["id"]
    assert logs[0]["messages_json"] is None


def test_legacy_cached_reply_is_not_mislabeled_as_original(cache):
    database.store_draft("t1", "m1", "Possibly already revised")
    database.store_draft("t1", "m1", "New revision", event_type="reprompt",
                         input_response="Possibly already revised", messages=[])
    log = database.get_generation_logs("t1")[0]
    assert log["first_draft_id"] is None
    assert log["input_response_text"] == "Possibly already revised"
