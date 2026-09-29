from copy import deepcopy
import asyncio
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


@pytest.mark.parametrize("contacts", [[], [{"id": "contact-1"}]])
def test_email_endpoint_awaits_lookup_with_path_email(api, monkeypatch, contacts):
    lookup = AsyncMock(return_value=contacts)
    tickets = [{"id": "ticket-1"}]
    ticket_lookup = AsyncMock(return_value=tickets)
    monkeypatch.setattr(api, "get_contacts_list_by_email", lookup)
    monkeypatch.setattr(api, "get_info_by_contacts", ticket_lookup)
    response = TestClient(api.app).get("/tickets/emails/customer%2Btag%40example.com")
    assert response.status_code == 200
    assert response.json() == {"data": tickets if contacts else []}
    lookup.assert_awaited_once()
    assert lookup.await_args.kwargs["email"] == "customer+tag@example.com"
    if contacts:
        ticket_lookup.assert_awaited_once()
        assert ticket_lookup.await_args.kwargs["contacts_id"] == "contact-1"
    else:
        ticket_lookup.assert_not_awaited()


def test_email_endpoint_checks_all_contacts_and_deduplicates_tickets(api, monkeypatch):
    monkeypatch.setattr(api, "get_contacts_list_by_email", AsyncMock(return_value=[
        {"id": 1}, {"id": 2}, {"id": 2}, {"id": 3},
    ]))
    lookup = AsyncMock(side_effect=[[], [{"id": 10}], [{"id": 10}, {"id": 11}]])
    monkeypatch.setattr(api, "get_info_by_contacts", lookup)
    response = TestClient(api.app).get("/tickets/emails/customer@example.com")
    assert response.status_code == 200
    assert response.json() == {"data": [{"id": 10}, {"id": 11}]}
    assert [call.kwargs["contacts_id"] for call in lookup.await_args_list] == [1, 2, 3]


def test_email_endpoint_contact_without_tickets_returns_empty(api, monkeypatch):
    monkeypatch.setattr(api, "get_contacts_list_by_email", AsyncMock(return_value=[{"id": 1}]))
    monkeypatch.setattr(api, "get_info_by_contacts", AsyncMock(return_value=[]))
    response = TestClient(api.app).get("/tickets/emails/customer@example.com")
    assert response.status_code == 200
    assert response.json() == {"data": []}


@pytest.mark.parametrize("resource", ["contacts", "tickets"])
@pytest.mark.parametrize("failure", ["http", "timeout", "json", "missing_data", "invalid_record"])
def test_email_lookup_upstream_failures_are_502(api, monkeypatch, resource, failure):
    request = httpx.Request("GET", f"https://api.edesk.com/v1/{resource}")
    response = httpx.Response(200, json={"data": [{"id": 1}]}, request=request)
    if failure == "http":
        response = httpx.Response(429, request=request)
    elif failure == "json":
        response = httpx.Response(200, text="not json", request=request)
    elif failure == "missing_data":
        response = httpx.Response(200, json={}, request=request)
    elif failure == "invalid_record":
        response = httpx.Response(200, json={"data": [{}]}, request=request)
    get = AsyncMock(return_value=response)
    if failure == "timeout":
        get.side_effect = httpx.ReadTimeout("timeout", request=request)
    monkeypatch.setattr(api.httpx.AsyncClient, "get", get)
    if resource == "tickets":
        monkeypatch.setattr(api, "get_contacts_list_by_email", AsyncMock(return_value=[{"id": 1}]))
    result = TestClient(api.app).get("/tickets/emails/customer@example.com")
    assert result.status_code == 502
    assert resource in result.json()["detail"]


def test_email_lookup_helpers_encode_query_parameters(api):
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": []})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await api.get_contacts_list_by_email(client, "customer+tag@example.com") == []
            assert await api.get_info_by_contacts(client, 123) == []
    asyncio.run(run())
    assert captured[0].url.params["email"] == "customer+tag@example.com"
    assert captured[1].url.params["filter_contact_id_equals"] == "123"


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


def test_api_preserves_first_reply_and_all_reprompts(api, monkeypatch):
    messages = [{"role": "Customer", "text": "My PC will not start."}]
    monkeypatch.setattr(api, "get_ticket_messages", AsyncMock(return_value=(messages, True, "m1")))
    api.generate_ticket_reply.return_value = {"reply": "Original", "sources": ["source1"]}
    revise = Mock(side_effect=["Short", "Formal"])
    monkeypatch.setattr(api, "reprompt_call", revise)
    client = TestClient(api.app)
    assert client.get("/tickets/t1/llm_response").status_code == 200
    assert client.get("/tickets/t1/llm_response").json()["cache_hit"] is True
    for before, instruction in [("Original", "Shorter"), ("Short", "More formal")]:
        assert client.post("/tickets/t1/reprompt", json={
            "instructions": instruction, "last_response": before,
        }).status_code == 200
    logs = database.get_generation_logs("t1")
    assert [row["response_text"] for row in logs] == ["Original", "Short", "Formal"]
    assert [row["instructions"] for row in logs] == ["", "Shorter", "More formal"]
    assert [row["input_response_text"] for row in logs] == [None, "Original", "Short"]
    assert all(json.loads(row["messages_json"]) == messages for row in logs)
    assert all(row["first_draft_id"] == logs[0]["id"] for row in logs[1:])
    assert database.get_cached_draft("t1", "m1") == "Formal"
    api.generate_ticket_reply.assert_called_once()
