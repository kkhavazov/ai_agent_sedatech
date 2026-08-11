from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from services.order_service import OrderService

from tools.orders.orders_filter_args import (
    DocumentStatus,
    DocumentType,
    LifecycleState,
    OrderFiltersArguments,
    resolve_lifecycle_filters,
)
class FilterOrdersArguments(OrderFiltersArguments):
    limit: int = Field(
        default=20,
        description=(
            "Maximum number of orders to return. "
            "Use 1 for requests asking for the latest or most recent order. "
            "If the number of returned orders equals the requested limit, "
            "the result may be truncated. Increase the limit and retry, "
            "up to a maximum of 100."
        ),
        ge=1,
        le=100,
    )
    

    sort_order: Literal["newest", "oldest"] = Field(
        default="newest",
        description=(
            "Sort by creation date. Use 'oldest' for the earliest order "
            "and 'newest' for the latest order."
        ),
    )

    @model_validator(mode="after")
    def require_at_least_one_filter(
        self,
    ) -> "FilterOrdersArguments":
        has_filter = any(
            value is not None
            for value in (
                self.lifecycle_state,
                self.order_number,
                self.document_type,
                self.status,
                self.customer_name,
                self.country,
                self.date_from,
                self.date_to,
            )
        )

        if not has_filter:
            raise ValueError(
                "At least one filter must be provided."
            )

        return self


class CountOrdersArguments(OrderFiltersArguments):
    """Arguments for counting matching orders."""
def create_filter_orders_handler(
    order_service: OrderService,
):
    def filter_orders_handler(
        lifecycle_state: LifecycleState | None = None,
        order_number: str | None = None,
        document_type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        customer_name: str | None = None,
        country: str | None = None,
        address: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_order: Literal["newest", "oldest"] = "newest",
        limit: int = 20,
    ) -> dict[str, Any]:
        resolved_document_type, resolved_status = (
            resolve_lifecycle_filters(
                lifecycle_state=lifecycle_state,
                document_type=document_type,
                status=status,
            )
        )

        orders = order_service.filter_orders(
            order_number=order_number,
            document_type=resolved_document_type,
            status=resolved_status,
            customer_name=customer_name,
            country=country,
            address=address,
            date_from=date_from,
            date_to=date_to,
            sort_order=sort_order,
            limit=limit,
        )

        returned_count = len(orders)

        return {
            "success": True,
            "returned_count": returned_count,
            "requested_limit": limit,
            "possibly_truncated": returned_count == limit,
            "requested_filters": {
                "lifecycle_state": lifecycle_state,
                "order_number": order_number,
                "document_type": document_type,
                "status": status,
                "customer_name": customer_name,
                "country": country,
                "address": address,
                "date_from": date_from,
                "date_to": date_to,
            },
            "resolved_database_filters": {
                "document_type": resolved_document_type,
                "status": resolved_status,
            },
            "orders": [
                {
                    "order_number": order.order_number,
                    "status": order.status,
                    "date": order.date,
                    "document_type": order.document_type,
                    "customer_name": order.customer_name,
                    "country": order.country,
                    "address": order.address,
                    "final_price": order.final_price,
                }
                for order in orders
            ],
        }

    return filter_orders_handler

def create_count_orders_handler(
    order_service: OrderService,
):
    def count_orders_handler(
        lifecycle_state: LifecycleState | None = None,
        order_number: str | None = None,
        document_type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        customer_name: str | None = None,
        country: str | None = None,
        address: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        resolved_document_type, resolved_status = (
            resolve_lifecycle_filters(
                lifecycle_state=lifecycle_state,
                document_type=document_type,
                status=status,
            )
        )

        count = order_service.count_orders(
            document_type=resolved_document_type,
            status=resolved_status,
            country=country,
            address=address,
            date_from=date_from,
            date_to=date_to,
        )

        return int(count)

    return count_orders_handler