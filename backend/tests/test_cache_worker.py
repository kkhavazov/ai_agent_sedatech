import asyncio
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

import database


@pytest.mark.parametrize("translation_status", [200, 502])
def test_deployed_warmer_translates_before_requesting_draft(monkeypatch, translation_status):
    monkeypatch.setenv("EDESK_API_KEY", "test")
    import script

    calls = []

    def respond(request):
        calls.append(request.url.path)
        status = translation_status if len(calls) == 1 else 200
        return httpx.Response(status, json={"cache_hit": True})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await script.generate_ticket_draft(client, "123", asyncio.Semaphore(1))

    assert asyncio.run(run()) is (translation_status == 200)
    assert calls == (["/tickets/123", "/tickets/123/llm_response"]
                     if translation_status == 200 else ["/tickets/123"])


@pytest.mark.parametrize("fail_translation", [False, True])
def test_standalone_worker_caches_messages_and_retries_translations(monkeypatch, tmp_path, fail_translation):
    monkeypatch.setenv("EDESK_API_KEY", "test")
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "cache.db")
    database.initialize_database()
    translate = Mock(side_effect=RuntimeError("translation failed") if fail_translation else None)
    draft = Mock(return_value="Bonjour")
    monkeypatch.setitem(sys.modules, "llm_requests", SimpleNamespace(translate_ticket_messages=translate))
    monkeypatch.setitem(sys.modules, "customer_support_agent", SimpleNamespace(generate_ticket_reply=draft))
    monkeypatch.delitem(sys.modules, "worker", raising=False)
    worker = importlib.import_module("worker")
    calls = []

    def respond(request):
        calls.append(request.url.path)
        direction = "Incoming" if request.url.path.endswith("1") else "Internal"
        return httpx.Response(200, json={"data": {"direction": direction, "body": "Hello"}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            first = await worker.process_single_ticket(client, "123", {"messages_ids": [1, 2]})
            translate.side_effect = None
            second = await worker.process_single_ticket(client, "123", {"messages_ids": [1, 2]})
            return first, second

    try:
        first, second = asyncio.run(run())
        assert bool(first["errors"]) is fail_translation
        assert second["errors"] == []
        assert first["messages_cached"] == 2
        assert second["messages_cached"] == 0
        assert calls == ["/v1/messages/1", "/v1/messages/2"]
        messages = [{"role": "Customer", "text": "Hello"}]
        assert database.get_cached_messages("123", ["1", "2"]) == messages
        assert translate.call_count == 2
        translate.assert_called_with(messages)
        draft.assert_called_once_with(messages, "123", "2")
        assert database.get_cached_draft("123", "2") == "Bonjour"
    finally:
        sys.modules.pop("worker", None)
