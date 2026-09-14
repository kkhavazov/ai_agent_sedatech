from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass(slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


class LLMClient(ABC):
    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError
