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
        result = service.find_for_order(order_number)
        return {
            "order_number": order_number.strip(),
            "has_missing_components": bool(result and result.components),
            "missing_components": asdict(result) if result else None,
        }

    return ToolDefinition(
        name="find_missing_components",
        description=(
            "Return components and quantities currently missing for one exact "
            "order. Use for 'what is missing for order X?' or 'what do we need "
            "for order X?' when an order number is given. For predicted future "
            "inventory needs, use forecast_components."
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
            "Return components and quantities currently missing across all open "
            "orders. Default tool for 'what are we missing?', 'what components "
            "are missing?', 'what do we need?', or 'what do we need to order?' "
            "without a specific order number or future period. The user does "
            "not need to mention open orders. For one exact order, use "
            "find_missing_components. Use forecast_components only for explicit "
            "predictions, forecasts, or future ordering needs."
        ),
        arguments_model=FindOpenOrderMissingComponentsArguments,
        handler=find_open_order_missing_components,
    )
