from pydantic import BaseModel

from tools.registry import ToolDefinition, ToolRegistry


class Arguments(BaseModel):
    value: int


def test_registry_validates_and_executes() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="double",
            description="Double an integer",
            arguments_model=Arguments,
            handler=lambda value: value * 2,
        )
    )

    result = registry.execute("double", {"value": 3})
    assert result["success"] is True
    assert result["data"] == 6


def test_registry_rejects_invalid_arguments() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="double",
            description="Double an integer",
            arguments_model=Arguments,
            handler=lambda value: value * 2,
        )
    )

    result = registry.execute("double", {"value": "invalid"})
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
