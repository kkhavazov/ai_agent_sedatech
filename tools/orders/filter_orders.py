from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator

from services.order_service import OrderService


class FilterOrdersArguments(BaseModel):
    order_number: str | None = Field(
        default=None,
        description=(
            "Full or partial order number, for example AG0950953."
        ),
        min_length=1,
        max_length=50,
    )

    document_type: str | None = Field(
        default=None,
        description="The type of order action(A = 'Unconfirmed', D = 'Confirmed', L = 'In production', R = 'Prepared/Sent')",
        min_length=1,
        max_length=10,
    )

    status: str | None = Field(
        default=None,
        description="Exact order status to filter by. 0 = order put into state, 2 = order finished this state",
        min_length=1,
        max_length=100,
    )

    customer_name: str | None = Field(
        default=None,
        description="Full or partial customer name.",
        min_length=1,
        max_length=200,
    )

    date_from: date | None = Field(
        default=None,
        description=(
            "Earliest order date, formatted strictly as YYYY-MM-DD. "
            "Warning: European inputs use DD.MM.YYYY. For example, "
            "if the user inputs '04.08.2026' for August 4th, you MUST "
            "format this as '2026-08-04'. Do not mix up month and day."
        ),
    )

    date_to: date | None = Field(
        default=None,
        description=(
            "Latest order date, formatted strictly as YYYY-MM-DD. "
            "Warning: European inputs use DD.MM.YYYY. For example, "
            "if the user inputs '04.08.2026' for August 4th, you MUST "
            "format this as '2026-08-04'. Do not mix up month and day."
        ),
    )

    limit: int = Field(
        default=20,
        description="Maximum number of orders to return.",
        ge=1,
        le=100,
    )

    @model_validator(mode="after")
    def validate_filters(self) -> "FilterOrdersArguments":
        has_filter = any(
            [
                self.order_number,
                self.document_type,
                self.status,
                self.customer_name,
                self.date_from,
                self.date_to,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one filter must be provided"
            )

        if (
            self.date_from
            and self.date_to
            and self.date_from > self.date_to
        ):
            raise ValueError(
                "date_from cannot be later than date_to"
            )

        return self


def create_filter_orders_handler(
    order_service: OrderService,
):
    def filter_orders_handler(
        order_number: str | None = None,
        document_type: str | None = None,
        status: str | None = None,
        customer_name: str | None = None,
        country: str | None = None,
        adress: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        orders = order_service.filter_orders(
            order_number=order_number,
            document_type=document_type,
            status=status,
            customer_name=customer_name,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

        return {
            "count": len(orders),
            "orders": [
                {
                    "order_number": order.order_number,
                    "status": order.status,
                    "document_type": order.document_type,
                    "customer_name": order.customer_name,
                    "country": order.country,
                    "adress": order.adress,
                }
                for order in orders
            ],
        }

    return filter_orders_handler