from __future__ import annotations

from dataclasses import dataclass, field
from models.order import OrderItem

@dataclass(slots=True)
class SearchItemResponse:
    total_count: int
    items: list[OrderItem] = field(default_factory=list)
