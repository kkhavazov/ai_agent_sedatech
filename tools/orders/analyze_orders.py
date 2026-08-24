from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from services.order_service import OrderService
from tools.orders.orders_filter_args import LIFECYCLE_FILTERS, LifecycleState


class AnalyzeOrdersDataArguments(BaseModel):
    lifecycle_state: LifecycleState | None = Field(
        default=None,
        description=(
            "Current operational lifecycle state. created_unconfirmed = A/0; "
            "confirmed_workshop = D/0; in_production = L/0; "
            "ready_or_sent = R/0. Use this for current-state questions."
        ),
    )
    date_from: date | None = None
    date_to: date | None = None
    document_type: Literal["A", "D", "L", "R"] | None = None
    status: int | None = Field(default=None, ge=0)
    max_rows: int = Field(default=1000, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_dates(self) -> "AnalyzeOrdersDataArguments":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be later than date_to")
        if self.lifecycle_state is not None:
            expected_type, expected_status = LIFECYCLE_FILTERS[
                self.lifecycle_state
            ]
            if self.document_type not in (None, expected_type):
                raise ValueError(
                    f"lifecycle_state={self.lifecycle_state!r} requires "
                    f"document_type={expected_type!r}"
                )
            if self.status not in (None, int(expected_status)):
                raise ValueError(
                    f"lifecycle_state={self.lifecycle_state!r} requires "
                    f"status={expected_status}"
                )
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
        lifecycle_state: LifecycleState | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: Literal["A", "D", "L", "R"] | None = None,
        status: int | None = None,
        max_rows: int = 1000,
    ) -> dict[str, Any]:
        if lifecycle_state is not None:
            document_type, resolved_status = LIFECYCLE_FILTERS[
                lifecycle_state
            ]
            status = int(resolved_status)
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
