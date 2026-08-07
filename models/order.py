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
    order_number: str
    document_type: str
    status: str
    date: datetime | None = None
    customer_name: str | None = None
    country: str | None = None
    address: str | None = None
    items: list[OrderItem] = field(default_factory=list)
