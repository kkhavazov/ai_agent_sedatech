from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from ollama import ResponseError

import database


@pytest.fixture
def translation(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "cache.db")
    database.initialize_database()
    with patch("qdrant_client.QdrantClient"), patch("ollama.Client"):
        import llm_requests
    client = Mock()
    monkeypatch.setattr(llm_requests, "ollama_client", client)
    return llm_requests, client


@pytest.fixture
def api(translation, monkeypatch):
    monkeypatch.setenv("EDESK_API_KEY", "test-key")
    import main
    monkeypatch.setattr(main, "get_remote_ticket", AsyncMock(return_value={}))
    monkeypatch.setattr(main, "generate_ticket_reply", Mock())
    return main


@pytest.mark.parametrize("cache_hit", [True, False])
def test_endpoint_translates_all_roles_and_reuses_translations(api, translation, monkeypatch, cache_hit):
    requests, client = translation
    originals = [
        {"role": "Customer", "text": "<p>My PC ABC123 will not start.</p>"},
        {"role": "Sedatech Support", "text": "Please check the power cable."},
        {"role": "Customer", "text": ""},
    ]
    before = deepcopy(originals)
    translated = ["<p>Mon PC ABC123 ne démarre pas.</p>", "Veuillez vérifier le câble d'alimentation."]
    client.chat.side_effect = [
        {"message": {"content": text}, "done_reason": "stop"}
        for text in translated
    ]
    monkeypatch.setattr(api, "get_ticket_messages", AsyncMock(return_value=(originals, cache_hit, "m3")))

    response = TestClient(api.app).get("/tickets/t1")
    repeated = TestClient(api.app).get("/tickets/t1")

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": "t1",
        "messages": [
            {"role": "Customer", "text": translated[0]},
            {"role": "Sedatech Support", "text": translated[1]},
            {"role": "Customer", "text": ""},
        ],
        "last_message_id": "m3",
        "cache_hit": cache_hit,
    }
    assert repeated.json() == response.json()
    assert originals == before
    api.generate_ticket_reply.assert_not_called()
    assert client.chat.call_count == 2
    for call, original in zip(client.chat.call_args_list, originals):
        kwargs = call.kwargs
        assert kwargs["model"] == requests.model_settings.ollama_model
        assert kwargs["think"] is False
        assert kwargs["options"]["temperature"] == 0
        assert "tools" not in kwargs
        assert kwargs["messages"][-1] == {"role": "user", "content": original["text"]}


def test_blank_messages_skip_ollama_and_changed_text_is_translated(translation):
    requests, client = translation
    assert requests.translate_to_french(" \n") == " \n"
    client.chat.assert_not_called()
    client.chat.return_value = {"message": {"content": "Bonjour"}}
    requests.translate_to_french("Hello")
    requests.translate_to_french("Hello again")
    requests.translate_to_french(" Hello ")
    assert client.chat.call_count == 3


def test_translation_survives_database_initialization_and_a_fresh_process(translation):
    requests, client = translation
    client.chat.return_value = {"message": {"content": "Bonjour"}, "done_reason": "stop"}
    assert requests.translate_to_french("Hello") == "Bonjour"

    database.initialize_database()
    assert requests.translate_to_french("Hello") == "Bonjour"
    client.chat.assert_called_once()

    # A new interpreter has no in-memory cache and must reuse the database.
    result = subprocess.run(
        [sys.executable, "-c", """
import json
from pathlib import Path
import sys
from unittest.mock import Mock, patch

with patch("qdrant_client.QdrantClient"), patch("ollama.Client"):
    import llm_requests
import database

database.DATABASE_PATH = Path(sys.argv[1])
database.initialize_database()
llm_requests.model_settings = Mock()
llm_requests.model_settings.chat_kwargs.return_value = json.loads(sys.argv[2])
llm_requests.ollama_client.chat.side_effect = AssertionError("A saved translation must not call Ollama")
assert llm_requests.translate_to_french("Hello") == "Bonjour"
llm_requests.ollama_client.chat.assert_not_called()
""", str(database.DATABASE_PATH), json.dumps(requests.model_settings.chat_kwargs())],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("changed_setting", [
    {"ollama_model": "different-translation-model"},
    {"ollama_num_ctx": 32768},
    {"ollama_num_predict": 4096},
])
def test_model_or_generation_options_change_invalidates_translation(translation, monkeypatch, changed_setting):
    requests, client = translation
    original_settings = requests.model_settings
    # Use explicit baselines so local environment overrides cannot make the
    # requested change identical to the original settings.
    baseline = replace(original_settings, ollama_model="translation-model", ollama_num_ctx=8192, ollama_num_predict=1024)
    monkeypatch.setattr(requests, "model_settings", baseline)
    client.chat.side_effect = [
        {"message": {"content": "Bonjour"}},
        {"message": {"content": "Salut"}},
    ]
    assert requests.translate_to_french("Hello") == "Bonjour"

    monkeypatch.setattr(requests, "model_settings", replace(baseline, **changed_setting))
    assert requests.translate_to_french("Hello") == "Salut"
    assert requests.translate_to_french("Hello") == "Salut"

    monkeypatch.setattr(requests, "model_settings", baseline)
    assert requests.translate_to_french("Hello") == "Bonjour"
    assert client.chat.call_count == 2


def test_prompt_change_invalidates_translation(translation, monkeypatch):
    requests, client = translation
    client.chat.side_effect = [
        {"message": {"content": "Bonjour"}},
        {"message": {"content": "Salut"}},
    ]
    assert requests.translate_to_french("Hello") == "Bonjour"

    monkeypatch.setattr(requests, "TRANSLATION_INSTRUCTIONS", requests.TRANSLATION_INSTRUCTIONS + "\nUse informal French.")
    assert requests.translate_to_french("Hello") == "Salut"
    assert requests.translate_to_french("Hello") == "Salut"
    assert client.chat.call_count == 2


def test_settings_that_do_not_affect_translation_reuse_the_cache(translation, monkeypatch):
    requests, client = translation
    client.chat.return_value = {"message": {"content": "Bonjour"}}
    assert requests.translate_to_french("Hello") == "Bonjour"

    monkeypatch.setattr(requests, "model_settings", replace(
        requests.model_settings,
        ollama_keep_alive="123m",
        ollama_temperature=0.7,
        ollama_think=True,
    ))
    assert requests.translate_to_french("Hello") == "Bonjour"
    client.chat.assert_called_once()


@pytest.mark.parametrize("error", [
    ConnectionError("unreachable"),
    httpx.ReadTimeout("timed out"),
    ResponseError("model unavailable", status_code=404),
])
def test_translation_errors_are_not_cached(translation, error):
    requests, client = translation
    client.chat.side_effect = [error, {"message": {"content": "Bonjour"}}]
    with pytest.raises(requests.TranslationError):
        requests.translate_to_french("Hello")
    assert requests.translate_to_french("Hello") == "Bonjour"
    assert requests.translate_to_french("Hello") == "Bonjour"
    assert client.chat.call_count == 2


@pytest.mark.parametrize("model_response", [
    {"message": {"content": ""}},
    {"message": {"content": " \n"}},
    {"message": {"content": "Traduction partielle"}, "done_reason": "length"},
])
def test_endpoint_rejects_incomplete_translations(api, translation, monkeypatch, model_response):
    _, client = translation
    client.chat.side_effect = [model_response, {"message": {"content": "Bonjour"}}]
    monkeypatch.setattr(api, "get_ticket_messages", AsyncMock(return_value=(
        [{"role": "Customer", "text": "Hello"}], True, "m1"
    )))
    response = TestClient(api.app).get("/tickets/t1")
    assert response.status_code == 502
    assert "Ollama" in response.json()["detail"]
    assert "messages" not in response.json()

    retry = TestClient(api.app).get("/tickets/t1")
    repeated = TestClient(api.app).get("/tickets/t1")
    assert retry.status_code == 200
    assert retry.json()["messages"] == [{"role": "Customer", "text": "Bonjour"}]
    assert repeated.json() == retry.json()
    assert client.chat.call_count == 2


def test_ticket_drafting_still_receives_original_messages(api, translation, monkeypatch):
    _, client = translation
    originals = [{"role": "Customer", "text": "My PC will not start."}]
    monkeypatch.setattr(api, "get_ticket_messages", AsyncMock(return_value=(originals, True, "m1")))
    monkeypatch.setattr(api, "get_cached_draft", Mock(return_value=None))
    monkeypatch.setattr(api, "store_draft", Mock())
    api.generate_ticket_reply.return_value = {"reply": "Bonjour", "sources": []}

    response = TestClient(api.app).get("/tickets/t1/llm_response")

    assert response.status_code == 200
    api.generate_ticket_reply.assert_called_once_with(originals, "t1", "m1")
    client.chat.assert_not_called()
