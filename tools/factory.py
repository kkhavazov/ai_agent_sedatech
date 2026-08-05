from __future__ import annotations

from services.order_service import OrderService
from tools.registry import ToolDefinition, ToolRegistry
from tools.order_tools import build_get_order_tool
from tools.registry import ToolRegistry
from tools.orders.filter_orders import (
    FilterOrdersArguments,
    create_filter_orders_handler,
)
from tools.current_time_tools import (
    create_current_time_handler,
    GetCurrentTimeArgs,
    )

def build_tool_registry(order_service: OrderService) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(build_get_order_tool(order_service))
    registry.register(
        ToolDefinition(
            name="filter_orders",
            description=(
                "Find orders when the exact order number is unknown. "
                "Search by customer name, partial order number, status, "
                "or date range. For example, to find orders for Nicolas "
                "Lungu, use customer_name='Nicolas Lungu'."
            ),
            arguments_model=FilterOrdersArguments,
            handler=create_filter_orders_handler(order_service),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_current_time",
            description=(
                "Find current time, location is Berlin/Germany"
            ),
            arguments_model=GetCurrentTimeArgs,
            handler=create_current_time_handler(order_service),
        )
    )
    return registry
