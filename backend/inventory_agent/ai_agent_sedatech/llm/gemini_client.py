from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from llm.base import LLMClient, LLMResponse, ToolCall


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.name = f"gemini:{model}"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        contents = self._convert_messages(messages)
        config_kwargs: dict[str, Any] = {}

        if tools:
            declarations = [
                types.FunctionDeclaration(
                    name=tool["function"]["name"],
                    description=tool["function"].get("description", ""),
                    parameters_json_schema=tool["function"]["parameters"],
                )
                for tool in tools
            ]
            config_kwargs["tools"] = [types.Tool(function_declarations=declarations)]

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        calls: list[ToolCall] = []
        content_parts: list[str] = []

        if response.candidates:
            candidate_content = response.candidates[0].content
            if candidate_content and candidate_content.parts:
                for part in candidate_content.parts:
                    if getattr(part, "text", None):
                        content_parts.append(part.text)
                    function_call = getattr(part, "function_call", None)
                    if function_call:
                        calls.append(
                            ToolCall(
                                name=function_call.name,
                                arguments=dict(function_call.args or {}),
                                call_id=getattr(function_call, "id", None),
                            )
                        )

        return LLMResponse(
            content="\n".join(content_parts).strip(),
            tool_calls=calls,
            raw=response,
        )

    @staticmethod
    def _convert_messages(messages: list[dict[str, Any]]) -> list[types.Content]:
        contents: list[types.Content] = []
        for message in messages:
            role = message["role"]
            if role == "system":
                # generate_content does not use a system role in contents here;
                # preserve it as initial user context for this minimal adapter.
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=message["content"])],
                    )
                )
            elif role in {"user", "assistant", "model"}:
                gemini_role = "model" if role in {"assistant", "model"} else "user"
                contents.append(
                    types.Content(
                        role=gemini_role,
                        parts=[types.Part.from_text(text=message.get("content", ""))],
                    )
                )
            elif role == "tool":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=message.get("content", ""))],
                    )
                )
        return contents
