from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from models.order import OrderItem
from models.item import ComponentForecast, ItemsSearchResponse
from repositories.item_repository import ItemRepository, normalize_skus

if TYPE_CHECKING:
    import pandas as pd


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
        gpu_manufacturer: Literal["NVIDIA", "AMD"] | None = None,
        gpu_series: Literal["GeForce", "Radeon", "Quadro", "Nvidia"] | None = None,
        gpu_model: str | None = None,
        gpu_vram: int | None = None,
    ) -> list[ItemsSearchResponse]:
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
                gpu_manufacturer,
                gpu_series,
                gpu_model,
                gpu_vram,
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
        return [
            ItemsSearchResponse(
                sku=item.sku,
                name=item.name,
                amount=item.quantity,
                ordered=0,
                minimum_price=float(item.price or 0),
                maximum_price=float(item.price or 0),
                average_price=float(item.price or 0),
            )
            for item in items
        ]

    def search_items_skus(self, list_of_skus: list[str]) -> dict[str, int]:
        stock = {item.sku.casefold(): item.quantity for item in self._items}
        return {
            sku: stock[sku.casefold()]
            for sku in normalize_skus(list_of_skus)
            if sku.casefold() in stock
        }

    def analyse_items_used(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        **filters: Any,
    ) -> pd.DataFrame:
        import pandas as pd

        # Demo stock has no sales history; do not invent sales from inventory.
        return pd.DataFrame(columns=["SKU", "Name", "SoldAmount", "Dates"])

    def get_components_forecast(
        self,
        weeks: int = 1,
    ) -> list[ComponentForecast]:
        return [
            ComponentForecast(
                sku="CP00001",
                name="Demo CPU",
                weekly_forecast=3.0 * weeks,
                stock_coverage=2.0 * weeks,
            )
        ]
