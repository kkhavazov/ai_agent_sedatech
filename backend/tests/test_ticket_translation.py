from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from ollama import ResponseError


@pytest.fixture
def translation(monkeypatch):
    with patch("qdrant_client.QdrantClient"), patch("ollama.Client"):
        import llm_requests
    llm_requests.translate_to_french.cache_clear()
    client = Mock()
    monkeypatch.setattr(llm_requests, "ollama_client", client)
    yield llm_requests, client
    llm_requests.translate_to_french.cache_clear()


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
    assert client.chat.call_count == 2


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
    assert client.chat.call_count == 2


@pytest.mark.parametrize("model_response", [
    {"message": {"content": ""}},
    {"message": {"content": " \n"}},
    {"message": {"content": "Traduction partielle"}, "done_reason": "length"},
])
def test_endpoint_rejects_incomplete_translations(api, translation, monkeypatch, model_response):
    _, client = translation
    client.chat.return_value = model_response
    monkeypatch.setattr(api, "get_ticket_messages", AsyncMock(return_value=(
        [{"role": "Customer", "text": "Hello"}], True, "m1"
    )))
    response = TestClient(api.app).get("/tickets/t1")
    assert response.status_code == 502
    assert "Ollama" in response.json()["detail"]
    assert "messages" not in response.json()


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
