from __future__ import annotations

from agent.state import AgentState


UNSAFE_PHRASES = (
    "I have issued the refund",
    "the refund has been issued",
    "I have cancelled the order",
    "your order has been cancelled",
)


def validate_draft(draft: str, state: AgentState) -> list[str]:
    warnings: list[str] = []
    lowered = draft.lower()

    for phrase in UNSAFE_PHRASES:
        if phrase.lower() in lowered:
            warnings.append(
                f"Draft may claim an unperformed action: {phrase!r}"
            )

    if not draft.strip():
        warnings.append("The model returned an empty draft")

    if state.tool_results and all(
        result.get("success") is False for result in state.tool_results
    ):
        warnings.append("All requested tools failed; verify the answer manually")

    return warnings
