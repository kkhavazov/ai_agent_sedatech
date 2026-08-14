from __future__ import annotations

from services.order_service import OrderService
from services.item_service import ItemService
from services.missing_service import MissingComponentService
from tools.registry import ToolDefinition, ToolRegistry
from tools.order_tools import build_get_order_tool
from tools.orders.filter_orders import (
    FilterOrdersArguments,
    create_filter_orders_handler,
    CountOrdersArguments,
    create_count_orders_handler,
)
from tools.items.search_item import (
    SearchItemsArguments,
    create_search_items_handler,
)
from tools.current_time_tools import (
    create_current_time_handler,
    GetCurrentTimeArgs,
)
from tools.missing_component_tools import (
    build_find_missing_components_tool,
    build_find_open_order_missing_components_tool,
)


def build_tool_registry(
    order_service: OrderService,
    item_service: ItemService | None = None,
    missing_component_service: MissingComponentService | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(build_get_order_tool(order_service))
    registry.register(
        ToolDefinition(
            name="filter_orders",
            description=(
                "Search and return order documents using order lifecycle filters. "
                "A business order progresses through A -> D -> L -> R, and may have "
                "multiple database document rows. "
                "Use lifecycle_state for current operational states. "
                "Ready for shipment, invoiced, or sent = lifecycle_state='ready_or_sent', "
                "which maps to document_type='R' and status='0'. "
                "Never pass an empty string for status. Omit status when it is unknown."
                "Use document_type and status directly for completed or historical "
                "stage searches. "
                "Examples: currently in production = L/0; entered production on a "
                "specific date = L with any status; finished production = L/2."
                "For the oldest or earliest matching order, call filter_orders with"
                "sort_order='oldest' and limit=1."
                "For the newest or latest matching order, call filter_orders with"
                "sort_order='newest' and limit=1."
            ),
            arguments_model=FilterOrdersArguments,
            handler=create_filter_orders_handler(order_service),
        )
    )
    registry.register(
        ToolDefinition(
            name="count_orders",
            description=(
                "Count orders or order documents matching lifecycle, customer, order "
                "number, or date filters. "
                "Use lifecycle_state for current operational counts. "
                "Examples: unconfirmed = A/0; confirmed workshop = D/0; "
                "currently in production = L/0; ready, invoiced, or sent = R/0. "
                "When searching whether orders entered a stage historically, filter "
                "by document_type without requiring status 0. "
                "Do not confuse the number of returned rows with the total count."
            ),
            arguments_model=CountOrdersArguments,
            handler=create_count_orders_handler(order_service),
        )
    )
    if item_service is not None:
        registry.register(
            ToolDefinition(
                name="search_item",
                description=(
                    "Return the number of inventory items matching the filters."
                ),
                arguments_model=SearchItemsArguments,
                handler=create_search_items_handler(item_service),
            )
        )
    if missing_component_service is not None:
        registry.register(
            build_find_missing_components_tool(missing_component_service)
        )
        registry.register(
            build_find_open_order_missing_components_tool(
                missing_component_service
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
