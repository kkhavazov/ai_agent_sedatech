from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from services.item_service import ItemService
from tools.items.search_item import SearchItemsArguments


SalesGrouping = Literal["day", "week", "month", "year", "total"]
ChartType = Literal["line", "bar"]
SOLD_AMOUNT_DESCRIPTION = (
    "Sum of matching component quantities on R (invoice) document lines within "
    "the inclusive invoice-date range. This measures recorded units sold, not "
    "revenue or stock removed during production. No rows means no matching "
    "recorded sales; it does not establish that an item is unknown. Only periods "
    "with matching invoice lines are returned; missing periods are not zero-filled."
)


class AnalyseItemsUsedArguments(SearchItemsArguments):
    date_from: date = Field(description="First invoice date, inclusive (YYYY-MM-DD).")
    date_to: date = Field(description="Last invoice date, inclusive (YYYY-MM-DD).")
    group_by: SalesGrouping = Field(
        default="month",
        description=(
            "Time bucket for each component's sold quantity. Period is the bucket's "
            "start date; weeks start on Monday. 'total' returns one total per "
            "component for the full requested range, with period=null."
        ),
    )
    chart_type: ChartType | None = Field(
        default=None,
        description=(
            "Set to 'line' or 'bar' when the user requests a graph; omit for a "
            "table only. Prefer bar for totals across components."
        ),
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "AnalyseItemsUsedArguments":
        if self.date_from > self.date_to:
            raise ValueError("date_from cannot be later than date_to")
        return self


def create_analyse_items_used_handler(item_service: ItemService):
    def handler(
        *,
        date_from: date,
        date_to: date,
        group_by: SalesGrouping = "month",
        chart_type: ChartType | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        args = AnalyseItemsUsedArguments(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            chart_type=chart_type,
            **filters,
        )
        rows = item_service.analyse_items_used(**args.model_dump(exclude={"chart_type"}))
        result = {
            "date_from": args.date_from.isoformat(),
            "date_to": args.date_to.isoformat(),
            "group_by": args.group_by,
            "requested_filters": args.model_dump(
                exclude={"date_from", "date_to", "group_by", "chart_type"},
                exclude_none=True,
            ),
            "row_count": len(rows),
            "rows": rows,
            "field_descriptions": {"sold_amount": SOLD_AMOUNT_DESCRIPTION},
        }
        if args.chart_type is not None and rows:
            total = args.group_by == "total"
            result["chart"] = {
                "type": args.chart_type,
                "title": (
                    f"Component sales ({args.date_from.isoformat()} to "
                    f"{args.date_to.isoformat()})"
                ),
                "x_label": "SKU / Article name" if total else "Period",
                "y_label": "Units sold",
                "x_type": "category" if total else "temporal",
                "data": [
                    {
                        "x": f'{row["sku"]} - {row["name"]}' if total else row["period"],
                        "y": row["sold_amount"],
                        "series": f'{row["sku"]} - {row["name"]}',
                    }
                    for row in rows
                ],
            }
        return result

    return handler
