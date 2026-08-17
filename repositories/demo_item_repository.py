from __future__ import annotations

from typing import Literal

from models.order import OrderItem
from repositories.item_repository import ItemRepository


class DemoItemRepository(ItemRepository):
    def __init__(self) -> None:
        self._items = [
            OrderItem(sku="CP00001", name="Demo CPU", quantity=5, price=199.0),
            OrderItem(sku="GC00001", name="Demo Graphics Card", quantity=2, price=499.0),
        ]

    def search_inventory(
        self,
        *,
        sku: str | None = None,
        manufacturer: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        ram_capacity: int | None = None,
        ram_ddr: int | None = None,
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: int | None = None,
        cpu_prefix: str | None = None,
        hdd_capacity: int | None = None,
        hdd_type: Literal["HDD", "SSD"] | None = None,
        case_manufacturer: str | None = None,
        case_model: str | None = None,
    ) -> int:
        items = self._items
        if sku:
            items = [item for item in items if sku.casefold() in item.sku.casefold()]
        if item_name:
            items = [item for item in items if item_name.casefold() in item.name.casefold()]
        if category:
            items = [item for item in items if item.sku.casefold().startswith(category.casefold())]
        if manufacturer:
            items = []
        if any(
            value is not None
            for value in (
                cpu_manufacturer,
                cpu_generation,
                cpu_model,
                cpu_prefix,
                hdd_capacity,
                hdd_type,
                case_manufacturer,
                case_model,
            )
        ):
            items = []
        if ram_capacity is not None:
            capacity_prefix = f"{ram_capacity}GB".casefold()
            items = [
                item
                for item in items
                if item.name.casefold().startswith(capacity_prefix)
            ]
        return len(items)
