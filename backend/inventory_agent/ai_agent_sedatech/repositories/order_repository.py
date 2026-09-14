from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Literal

from models.order import Order, OrderItem


class OrderRepository(ABC):
    @abstractmethod
    def find_by_order_number(self, order_number: str) -> Order | None:
        raise NotImplementedError

    @abstractmethod
    def filter_orders(
        self,
        *,
        order_number: str | None = None,
        document_type: str | None = None,
        status: int | None = None,
        customer_name: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_order: Literal["newest", "oldest"] = "newest",
        limit: int = 20,
    ) -> list[Order]:
        raise NotImplementedError

    @abstractmethod
    def analyze_orders_data(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: str | None = None,
        status: int | None = None,
        max_rows: int = 10000,
    ) -> Any:
        """Return tabular order data for aggregate analysis."""
        raise NotImplementedError
