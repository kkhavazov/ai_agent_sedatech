from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, Field

from services.missing_service import MissingComponentService
from tools.registry import ToolDefinition


class FindMissingComponentsArguments(BaseModel):
    order_number: str = Field(
        min_length=1,
        max_length=50,
        description="The exact order number to check",
    )


class FindOpenOrderMissingComponentsArguments(BaseModel):
    pass


def build_find_missing_components_tool(
    service: MissingComponentService,
) -> ToolDefinition:
    def find_missing_components(order_number: str) -> dict:
        components = service.find_for_order(order_number)
        return {
            "order_number": order_number.strip(),
            "has_missing_components": bool(components),
            "missing_components": [asdict(component) for component in components],
        }

    return ToolDefinition(
        name="find_missing_components",
        description=(
            "Check whether one exact order is currently missing any required "
            "components. Use this when the employee provides an order number."
        ),
        arguments_model=FindMissingComponentsArguments,
        handler=find_missing_components,
    )


def build_find_open_order_missing_components_tool(
    service: MissingComponentService,
) -> ToolDefinition:
    def find_open_order_missing_components() -> dict:
        components = service.find_for_open_orders()
        affected_orders = sorted(
            {component.order_number for component in components}
        )
        return {
            "has_missing_components": bool(components),
            "affected_order_count": len(affected_orders),
            "affected_orders": affected_orders,
            "missing_components": [asdict(component) for component in components],
        }

    return ToolDefinition(
        name="find_missing_components_for_open_orders",
        description=(
            "Find missing components across all orders that are currently open. "
            "Use this for fleet-wide questions without a specific order number."
        ),
        arguments_model=FindOpenOrderMissingComponentsArguments,
        handler=find_open_order_missing_components,
    )
