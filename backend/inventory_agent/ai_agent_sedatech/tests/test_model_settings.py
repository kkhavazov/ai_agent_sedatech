import os
from unittest.mock import Mock, patch

import pytest

from config import Settings
from model_settings import ModelSettings
from llm.ollama_client import OllamaClient


def test_environment_is_read_at_construction():
    with patch.dict(os.environ, {}, clear=True):
        assert ModelSettings().ollama_model == "qwen3.5:9b"
        os.environ.update({"OLLAMA_MODEL": "test-model", "OLLAMA_NUM_CTX": "32768"})
        assert Settings().ollama_model == "test-model"
        assert Settings().ollama_num_ctx == 32768


@pytest.mark.parametrize("name,value", [
    ("OLLAMA_NUM_CTX", "0"),
    ("OLLAMA_TIMEOUT_SECONDS", "bad"),
    ("OLLAMA_THINK", "maybe"),
    ("OLLAMA_TEMPERATURE", "nan"),
    ("OLLAMA_MODEL", ""),
])
def test_invalid_settings_fail_early(name, value):
    with patch.dict(os.environ, {name: value}, clear=True):
        with pytest.raises(ValueError):
            ModelSettings()


def test_inventory_payload_uses_shared_settings():
    with patch.dict(os.environ, {}, clear=True):
        settings = ModelSettings(
            ollama_model="test-model", ollama_num_ctx=32768,
            ollama_num_predict=1024, ollama_think=True,
            ollama_keep_alive="10m", ollama_timeout_seconds=45,
        )
    client = OllamaClient(settings.ollama_base_url, settings.ollama_model, settings=settings)
    response = Mock()
    response.json.return_value = {"message": {"content": "Hello"}}
    with patch("llm.ollama_client.requests.post", return_value=response) as post:
        assert client.chat([{"role": "user", "content": "Hi"}]).content == "Hello"
    payload = post.call_args.kwargs["json"]
    for name, value in settings.chat_kwargs().items():
        assert payload[name] == value
    assert post.call_args.kwargs["timeout"] == 45
