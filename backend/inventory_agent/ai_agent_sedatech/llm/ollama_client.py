from __future__ import annotations

from typing import Any

import requests

from llm.base import LLMClient, LLMResponse, ToolCall
from model_settings import ModelSettings


class OllamaClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int | None = None,
        settings: ModelSettings | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.settings = settings or ModelSettings()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self.settings.ollama_timeout_seconds
        self.name = f"ollama:{model}"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": self.settings.ollama_options(),
            "think": self.settings.ollama_think,
            "keep_alive": self.settings.ollama_keep_alive,
        }
        if tools:
            payload["tools"] = tools

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        data = response.json()
        # import json
        # print(json.dumps(data, indent=2, ensure_ascii=False))
        message = data.get("message", {})
        calls: list[ToolCall] = []

        for call in message.get("tool_calls", []) or []:
            function = call.get("function", {})
            calls.append(
                ToolCall(
                    name=function.get("name", ""),
                    arguments=function.get("arguments", {}) or {},
                )
            )

        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=calls,
            raw=data,
        )
