from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

@dataclass(slots=True)
class OrderItem:
    sku: str
    name: str
    quantity: int
    price: float | None = None
    sub_items: list[OrderItem] = field(default_factory=list)

    


@dataclass(slots=True)
class Order:
    document_number: str
    document_type: str
    status: int
    date_created: datetime | None = None
    customer_name: str | None = None
    country: str | None = None
    address: str | None = None
    selling_price: float | None = None
    items: list[OrderItem] = field(default_factory=list)
    tracking_number: str | None = None
    tax_number: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    language: str | None = None
    platform: str | None = None
    order_number: str | None = None
    production_cost: float | None = None
    gross_profit: float | None = None

    @property
    def final_price(self) -> float | None:
        """Compatibility alias for the selling price."""
        return self.selling_price

    @property
    def date(self) -> datetime | None:
        """Compatibility alias for the order/document creation date."""
        return self.date_created
