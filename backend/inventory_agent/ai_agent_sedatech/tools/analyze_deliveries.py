from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from repositories.delivery_repository import DeliveryComponent, DeliveryStatus
from services.delivery_service import DeliveryService
from tools.items.search_item import SearchItemsArguments
from tools.registry import ToolDefinition


class DeliveryComponentFilters(SearchItemsArguments):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalyzeDeliveriesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    components: list[Annotated[str, Field(min_length=1)] | DeliveryComponentFilters] = Field(
        default_factory=list,
        description=(
            "Match any listed component. Strings are full or partial SKUs. Objects "
            "use the same filters as search_item: sku, item_name, category, and "
            "RAM/CPU/storage/case/GPU attributes. Fields within an object combine "
            "with AND. Example: [{\"ram_capacity\": 16, \"ram_ddr\": 5}]. "
            "Empty means all components."
        ),
    )
    date_from: date | None = Field(
        default=None,
        description="Inclusive YYYY-MM-DD start for supplier document date (BP.Datum), not arrival date.",
    )
    date_to: date | None = Field(default=None, description="Inclusive YYYY-MM-DD end, using the same delivery date.")
    provider: str | None = Field(default=None, min_length=1, description="Exact supplier name; omit for all providers.")
    status: DeliveryStatus | None = Field(
        default=None,
        description="waiting (pending, UebernahmeOffen < 0) or received (arrived, UebernahmeOffen >= 0); omit for both.",
    )
    limit: int = Field(default=1000, ge=1, le=10000)

    @model_validator(mode="after")
    def validate_dates(self) -> "AnalyzeDeliveriesArguments":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be later than date_to")
        return self


def create_analyze_deliveries_handler(service: DeliveryService):
    def analyze_deliveries_handler(
        components: list[DeliveryComponent] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        provider: str | None = None,
        status: DeliveryStatus | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        frame, truncated = service.analyze_deliveries(
            components=components or [], date_from=date_from, date_to=date_to,
            provider=provider, status=status, limit=limit,
        )
        # pandas normalizes timestamps, numpy numbers, and missing values.
        rows = json.loads(frame.to_json(orient="records", date_format="iso"))
        return {
            "order_type": "incoming_delivery",
            "date_basis": "supplier_document_date",
            "columns": list(frame.columns),
            "row_count": len(rows),
            "rows": rows,
            "truncated": truncated,
        }

    return analyze_deliveries_handler


def build_analyze_deliveries_tool(service: DeliveryService) -> ToolDefinition:
    return ToolDefinition(
        name="analyze_deliveries",
        description=(
            "Return a table of incoming supplier deliveries for our inventory, "
            "filtered by partial SKUs or the same article attributes as search_item, "
            "inclusive delivery dates, provider, and "
            "received/waiting status. Dates use supplier document date (BP.Datum), "
            "not actual or expected arrival. Rows are component lines, "
            "not counts of distinct deliveries. These are purchases we receive; "
            "customer sales belong to analyze_data/filter_orders/count_orders. "
            "If the order direction is unclear from the conversation, first ask "
            "whether the user means customer sales or incoming supplier deliveries. "
            "Disclose truncated results; do not report them as complete totals."
        ),
        arguments_model=AnalyzeDeliveriesArguments,
        handler=create_analyze_deliveries_handler(service),
    )
