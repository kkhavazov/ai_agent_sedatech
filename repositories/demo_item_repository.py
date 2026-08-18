from __future__ import annotations

from typing import Literal

from models.order import OrderItem
from models.item import ItemsSearchResponse
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
        ram_speed: int | None = None,
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: int | None = None,
        cpu_prefix: str | None = None,
        hdd_capacity: int | None = None,
        hdd_type: Literal["HDD", "SSD"] | None = None,
        case_manufacturer: str | None = None,
        case_model: str | None = None,
    ) -> ItemsSearchResponse:
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
        if ram_ddr is not None:
            ddr_marker = f"DDR{ram_ddr}".casefold()
            items = [item for item in items if ddr_marker in item.name.casefold()]
        if ram_speed is not None:
            speed_marker = str(ram_speed)
            items = [item for item in items if speed_marker in item.name]
        prices = [item.price for item in items if item.price is not None]
        return ItemsSearchResponse(
            amount=sum(item.quantity for item in items),
            ordered=0,
            minimum_price=min(prices, default=0.0),
            maximum_price=max(prices, default=0.0),
            average_price=sum(prices) / len(prices) if prices else 0.0,
        )
