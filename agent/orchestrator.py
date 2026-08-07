from __future__ import annotations

import json

from agent.prompts import SYSTEM_PROMPT
from agent.state import AgentState
from agent.validators import validate_draft
from llm.model_router import ModelRouter
from models.agent_response import AgentResponse
from tools.registry import ToolRegistry


class SupportAgent:
    def __init__(
        self,
        model_router: ModelRouter,
        tool_registry: ToolRegistry,
        max_tool_rounds: int = 4,
    ) -> None:
        self.model_router = model_router
        self.tool_registry = tool_registry
        self.max_tool_rounds = max_tool_rounds

    def handle_request(self, request: str) -> AgentResponse:
        if not request.strip():
            raise ValueError("request cannot be empty")

        state = AgentState(user_request=request.strip())
        state.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": state.user_request},
        ]

        client = self.model_router.select(state.user_request)
        final_text = ""

        # TESTING CODE
        # for round_number in range(self.max_tool_rounds + 1):
        #     response = client.chat(
        #         messages=state.messages,
        #         tools=self.tool_registry.schemas(),
        #     )

        #     print(f"\n--- Agent round {round_number + 1} ---")
        #     print("Model content:", repr(response.content))
        #     print(
        #         "Tool calls:",
        #         [
        #             {
        #                 "name": call.name,
        #                 "arguments": call.arguments,
        #             }
        #             for call in response.tool_calls
        #         ],
        #     )

            # if not response.tool_calls:
            #     final_text = response.content.strip()
            #     break
            # for call in response.tool_calls:
            #     result = self.tool_registry.execute(
            #         call.name,
            #         call.arguments,
            #     )

            #     print(
            #         f"Tool result for {call.name}:",
            #         json.dumps(
            #             result,
            #             indent=2,
            #             ensure_ascii=False,
            #             default=str,
            #         ),
            #     )


        for _ in range(self.max_tool_rounds + 1):
            response = client.chat(
                messages=state.messages,
                tools=self.tool_registry.schemas(),
            )

            if not response.tool_calls:
                final_text = response.content.strip()
                break

            assistant_message = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "function": {
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                    }
                    for call in response.tool_calls
                ],
            }

            state.messages.append(assistant_message)

            for call in response.tool_calls:
                result = self.tool_registry.execute(call.name, call.arguments)
                state.tool_calls.append(
                    {"name": call.name, "arguments": call.arguments}
                )
                state.tool_results.append(result)
                state.messages.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
        else:
            state.warnings.append("Maximum number of tool rounds was reached")

        if not final_text:
            final_text = (
                "I could not produce a final draft. Please review the tool results "
                "and handle this request manually."
            )

        state.warnings.extend(validate_draft(final_text, state))
        return AgentResponse(
            draft=final_text,
            model_name=client.name,
            tool_calls=state.tool_calls,
            tool_results=state.tool_results,
            warnings=state.warnings,
        )
