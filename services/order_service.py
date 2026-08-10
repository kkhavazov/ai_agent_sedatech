from __future__ import annotations

from models.order import Order
from repositories.order_repository import OrderRepository


class OrderNotFoundError(LookupError):
    pass


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    def get_order(self, order_number: str) -> Order:
        normalized = order_number.strip()
        if not normalized:
            raise ValueError("order_number cannot be empty")

        order = self.repository.find_by_order_number(normalized)
        if order is None:
            raise OrderNotFoundError(f"Order {normalized} was not found")
        return order

    from datetime import date


    def filter_orders(
        self,
        *,
        order_number: str | None = None,
        document_type: str | None = None,
        status: int | None = None,
        customer_name: str | None = None,
        country: str | None = None,
        address: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_order: Literal["newest", "oldest"] = "newest",
        limit: int = 20,
    ) -> list[Order]:
        if date_from and date_to and date_from > date_to:
            raise ValueError(
                "date_from cannot be later than date_to"
            )
        has_filter = any(
            [
                order_number,
                status,
                document_type,
                customer_name,
                sort_order,
                date_from,
                date_to,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one order filter must be provided"
            )

        safe_limit = max(1, min(limit, 100))

        return self.repository.filter_orders(
            order_number=order_number,
            document_type=document_type,
            status=status,
            customer_name=customer_name,
            date_from=date_from,
            date_to=date_to,
            sort_order=sort_order,
            limit=safe_limit,
        )
    def count_orders(
        self,
        *,
        document_type: str | None = None,
        status: int | None = None,
        country: str | None = None,
        address: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> int:
        if date_from and date_to and date_from > date_to:
            raise ValueError(
                "date_from cannot be later than date_to"
            )
        has_filter = any(
            [
                status,
                document_type,
                date_from,
                date_to,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one order filter must be provided"
            )


        return self.repository.count_orders(
            document_type=document_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
