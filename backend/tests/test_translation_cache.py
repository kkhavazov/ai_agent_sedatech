import sqlite3

import pytest

import database


@pytest.fixture
def cache_path(tmp_path, monkeypatch):
    path = tmp_path / "cache.db"
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    database.initialize_database()
    return path


def test_translation_migration_preserves_existing_ticket_messages_and_drafts(cache_path):
    message = {"role": "Customer", "text": "My PC will not start."}
    draft = {"reply": "Bonjour", "sources": []}
    database.store_ticket_messages("ticket-1", ["message-1"], {"message-1": message})
    database.store_draft("ticket-1", "message-1", draft)
    # Recreate the database state from before translation caching was added.
    with sqlite3.connect(cache_path) as connection:
        connection.execute("DROP TABLE translations")

    database.initialize_database()
    database.initialize_database()

    assert database.get_ticket_revision("ticket-1") == "message-1"
    assert database.get_cached_messages("ticket-1", ["message-1"]) == [message]
    assert database.get_cached_draft("ticket-1", "message-1") == draft
    database.store_translation("translation-key", "Bonjour")
    assert database.get_cached_translation("translation-key") == "Bonjour"


def test_translation_cache_survives_reinitialization_and_updates_existing_keys(cache_path):
    assert database.get_cached_translation("missing-key") is None
    database.store_translation("translation-key", "Bonjour")
    database.store_translation("translation-key", "Salut")
    database.store_translation("other-key", "Au revoir")

    database.initialize_database()

    assert database.get_cached_translation("translation-key") == "Salut"
    assert database.get_cached_translation("other-key") == "Au revoir"
    with sqlite3.connect(cache_path) as connection:
        rows = connection.execute("SELECT created_at FROM translations").fetchall()
    assert len(rows) == 2
    assert all(row[0] for row in rows)
