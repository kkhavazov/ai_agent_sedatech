from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from services.order_service import OrderService
Metric = Literal["revenue", "order_count", "average_production_time"]
GroupBy = Literal["year", "month", "platform", "country", "city", "postcode"]


class AnalyzeDataArguments(BaseModel):
    metrics: list[Metric] = Field(
        default_factory=lambda: [
            "revenue", "order_count", "average_production_time"
        ], min_length=1
    )
    group_by: list[GroupBy] = Field(
        default_factory=lambda: ["year", "month"]
    )
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)
    date_from: date | None = None
    date_to: date | None = None
    document_type: Literal["A", "D", "L", "R"] | None = "R"
    status: int | None = Field(default=None, ge=0)
    sort_by: str | None = None
    sort_direction: Literal["asc", "desc"] = "asc"
    limit: int | None = Field(default=None, ge=1, le=10000)

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def expand_month_date(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        if (
            info.field_name == "date_to"
            and isinstance(value, str)
            and value.strip().casefold() in {"today", "now", "current date"}
        ):
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
            return value
        year, month = (int(part) for part in value.split("-"))
        if not 1 <= month <= 12:
            raise ValueError("month must be between 01 and 12")
        day = 1
        if info.field_name == "date_to":
            day = calendar.monthrange(year, month)[1]
        return date(year, month, day)

    @model_validator(mode="before")
    @classmethod
    def promote_date_filters(cls, values: Any) -> Any:
        if not isinstance(values, dict) or not isinstance(values.get("filters"), dict):
            return values
        values = dict(values)
        filters = dict(values["filters"])
        for field_name in ("date_from", "date_to"):
            filter_value = filters.pop(field_name, None)
            if values.get(field_name) in (None, "") and filter_value not in (None, ""):
                values[field_name] = filter_value
        values["filters"] = filters
        return values

    @model_validator(mode="after")
    def validate_dates(self) -> "AnalyzeDataArguments":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be later than date_to")
        allowed_sort_fields = set(self.group_by) | set(self.metrics)
        if self.sort_by is not None and self.sort_by not in allowed_sort_fields:
            raise ValueError("sort_by must be one of the requested metrics or groups")
        return self


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    # pandas uses NaN/NaT for missing values; neither is valid useful JSON data.
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value


def create_analyze_data_handler(order_service: OrderService):
    def analyze_data_handler(
        metrics: list[Metric],
        group_by: list[GroupBy] | None = None,
        filters: dict[str, str | int | float | bool] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: Literal["A", "D", "L", "R"] | None = "R",
        status: int | None = None,
        sort_by: str | None = None,
        sort_direction: Literal["asc", "desc"] = "asc",
        limit: int | None = None,
    ) -> dict[str, Any]:
        group_by = list(group_by or [])
        if "month" in group_by and "year" not in group_by:
            group_by.insert(0, "year")
        frame = order_service.analyze_data(
            metrics=metrics,
            group_by=group_by,
            filters=filters or {},
            date_from=date_from,
            date_to=date_to,
            document_type=document_type,
            status=status,
            sort_by=sort_by,
            sort_direction=sort_direction,
            limit=limit,
        )
        records = [
            {key: _json_safe(value) for key, value in record.items()}
            for record in frame.to_dict(orient="records")
        ]
        return {
            "row_count": len(records),
            "rows": records,
        }

    return analyze_data_handler


# Compatibility aliases for integrations importing the former Python symbols.
AnalyzeOrdersDataArguments = AnalyzeDataArguments
create_analyze_orders_data_handler = create_analyze_data_handler
