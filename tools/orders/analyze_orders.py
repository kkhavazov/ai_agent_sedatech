from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from services.order_service import OrderService


class AnalyzeOrdersDataArguments(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    document_type: Literal["A", "D", "L", "R"] | None = None
    status: int | None = Field(default=None, ge=0)
    max_rows: int = Field(default=1000, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_dates(self) -> "AnalyzeOrdersDataArguments":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be later than date_to")
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


def create_analyze_orders_data_handler(order_service: OrderService):
    def analyze_orders_data_handler(
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: Literal["A", "D", "L", "R"] | None = None,
        status: int | None = None,
        max_rows: int = 1000,
    ) -> dict[str, Any]:
        frame = order_service.analyze_orders_data(
            date_from=date_from,
            date_to=date_to,
            document_type=document_type,
            status=status,
            max_rows=max_rows,
        )
        records = [
            {key: _json_safe(value) for key, value in record.items()}
            for record in frame.to_dict(orient="records")
        ]
        return {
            "row_count": len(records),
            "max_rows": max_rows,
            "possibly_truncated": len(records) == max_rows,
            "rows": records,
        }

    return analyze_orders_data_handler
