from models.item import MissingComponent
from repositories.missing_repository import MissingRepository
from services.missing_service import MissingComponentService
from tools.missing_component_tools import (
    build_find_missing_components_tool,
    build_find_open_order_missing_components_tool,
)


class StubMissingRepository(MissingRepository):
    def find_missing_components(
        self,
        order_number: str,
    ) -> list[MissingComponent] | None:
        if order_number == "LS100":
            return [MissingComponent(order_number, "CP123")]
        return None

    def find_missing_components_for_open_orders(
        self,
    ) -> list[MissingComponent] | None:
        return [
            MissingComponent("LS100", "CP123"),
            MissingComponent("LS100", "ME456"),
            MissingComponent("LS200", "MB789"),
        ]


def test_find_missing_components_tool_serializes_results() -> None:
    service = MissingComponentService(StubMissingRepository())
    tool = build_find_missing_components_tool(service)

    result = tool.handler(order_number=" LS100 ")

    assert result == {
        "order_number": "LS100",
        "has_missing_components": True,
        "missing_components": [
            {"order_number": "LS100", "component": "CP123"}
        ],
    }


def test_find_missing_components_tool_reports_no_missing_items() -> None:
    service = MissingComponentService(StubMissingRepository())
    tool = build_find_missing_components_tool(service)

    result = tool.handler(order_number="LS999")

    assert result["has_missing_components"] is False
    assert result["missing_components"] == []


def test_open_order_tool_groups_affected_orders() -> None:
    service = MissingComponentService(StubMissingRepository())
    tool = build_find_open_order_missing_components_tool(service)

    result = tool.handler()

    assert result["affected_order_count"] == 2
    assert result["affected_orders"] == ["LS100", "LS200"]
    assert len(result["missing_components"]) == 3
