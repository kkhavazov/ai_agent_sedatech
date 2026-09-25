from __future__ import annotations

from models.item import ORDERED_AMOUNT_DESCRIPTION
from repositories.sqlserver_emails_repository import SqlServerEmailsRepository
from tools.email_tools import build_get_emails_tool
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
from tools.items.search_items_skus import (
    SearchItemsSkusArguments,
    create_search_items_skus_handler,
)
from tools.items.analyse_items_used import (
    AnalyseItemsUsedArguments,
    create_analyse_items_used_handler,
)
from tools.items.forecast_components import (
    ForecastComponentsArguments,
    create_forecast_components_handler,
)
from tools.current_time_tools import (
    create_current_time_handler,
    GetCurrentTimeArgs,
)
from tools.missing_component_tools import (
    build_find_missing_components_tool,
    build_find_open_order_missing_components_tool,
)
from tools.orders.analyze_orders import (
    AnalyzeDataArguments,
    create_analyze_data_handler,
)


def build_tool_registry(
    order_service: OrderService,
    item_service: ItemService | None = None,
    missing_component_service: MissingComponentService | None = None,
    emails_repository: SqlServerEmailsRepository | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    if emails_repository is not None:
        registry.register(build_get_emails_tool(emails_repository))
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
            name="analyze_data",
            description=(
                "Return row-level order data for analysis, grouping, trends, "
                "revenue calculations, and breakdowns by platform, country, "
                "status, or date. Use lifecycle_state for current operational "
                "stages: created_unconfirmed=A/0, confirmed_workshop=D/0, "
                "in_production=L/0, ready_or_sent=R/0. For historical stage "
                "activity use document_type without status; completed A, D, or L "
                "stages use status=2. Prefer count_orders for a simple count and "
                "filter_orders when order identities or details are requested."
            ),
            arguments_model=AnalyzeDataArguments,
            handler=create_analyze_data_handler(order_service),
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
                    "Return each available article matching the filters, grouped "
                    "by article number and name, with its SKU, inventory amount, "
                    "ordered amount, and price statistics. "
                    "Use for broader inventory analysis, partial SKU searches, "
                    "and component filters. For stock quantities of exact SKUs "
                    "only, use search_items_skus. For historical component "
                    "sales over time, use analyse_items_used. "
                    "The ordered field means: " + ORDERED_AMOUNT_DESCRIPTION
                ),
                arguments_model=SearchItemsArguments,
                handler=create_search_items_handler(item_service),
            )
        )
        registry.register(
            ToolDefinition(
                name="search_items_skus",
                description=(
                    "Return current stock quantities for a list of exact item "
                    "SKUs. Use when only SKU-based stock amounts are requested "
                    "or the user provides bare SKUs without another request. "
                    "Known SKUs with zero stock are included in stock; unknown "
                    "SKUs are listed separately in missing_skus. For broader "
                    "inventory analysis, item attributes, or price statistics, "
                    "use search_item."
                ),
                arguments_model=SearchItemsSkusArguments,
                handler=create_search_items_skus_handler(item_service),
            )
        )
        registry.register(
            ToolDefinition(
                name="analyse_items_used",
                description=(
                    "Return quantities sold for specific components, grouped by "
                    "SKU and day, week, month, year, or the full requested period. "
                    "Use for historical component sales tables and graph data. "
                    "Set chart_type to line or bar when a graph is requested. "
                    "Requires an inclusive invoice-date range and at least one "
                    "component filter. sold_amount sums invoice (R) line quantities; "
                    "it is not revenue or production stock usage. Empty rows mean "
                    "no matching recorded sales."
                ),
                arguments_model=AnalyseItemsUsedArguments,
                handler=create_analyse_items_used_handler(item_service),
            )
        )
        registry.register(
            ToolDefinition(
                name="forecast_components",
                description=(
                    "Forecast which PC components should be ordered for the "
                    "requested number of upcoming weeks. Use only for explicit "
                    "predictions, forecasts, or future ordering questions such as "
                    "'what do we need to order next week?'. For 'what are we "
                    "missing?', 'what do we need?', or 'what do we need to order?' "
                    "without a future period, use "
                    "find_missing_components_for_open_orders (or "
                    "find_missing_components for one exact order). "
                    "Returns only components "
                    "whose forecast demand exceeds current and incoming stock; "
                    "forecast_demand is the estimated total usage over the entire "
                    "requested period, not current stock. "
                    "suggested_order_quantity is forecast_demand minus current "
                    "stock and incoming supplier orders."
                ),
                arguments_model=ForecastComponentsArguments,
                handler=create_forecast_components_handler(item_service),
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
