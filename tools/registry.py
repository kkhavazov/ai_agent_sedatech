from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[..., Any]

    def ollama_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_model.model_json_schema(),
            },
        }

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool is already registered: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.ollama_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return self._error(name, "UNKNOWN_TOOL", f"Unknown tool: {name}")

        try:
            validated = tool.arguments_model.model_validate(arguments)
            data = tool.handler(**validated.model_dump())
            return {
                "success": True,
                "tool": name,
                "data": data,
                "error": None,
            }
        except ValidationError as exc:
            return self._error(name, "INVALID_ARGUMENTS", str(exc))
        except LookupError as exc:
            return self._error(name, "NOT_FOUND", str(exc))
        except Exception as exc:  # boundary: convert tool failures to structured data
            return self._error(name, "TOOL_EXECUTION_ERROR", str(exc))

    @staticmethod
    def _error(name: str, code: str, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "tool": name,
            "data": None,
            "error": {"code": code, "message": message},
        }
