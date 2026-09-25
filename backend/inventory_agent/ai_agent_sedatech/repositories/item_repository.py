from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from models.item import ComponentForecast, ItemsSearchResponse

if TYPE_CHECKING:
    import pandas as pd


def normalize_skus(list_of_skus: list[str]) -> list[str]:
    if not isinstance(list_of_skus, list) or len(list_of_skus) > 500:
        raise ValueError("list_of_skus must be a list with at most 500 SKUs")
    if any(not isinstance(sku, str) or not sku.strip() for sku in list_of_skus):
        raise ValueError("Each SKU must be a non-empty string")
    return list(dict.fromkeys(sku.strip() for sku in list_of_skus))


class ItemRepository(ABC):
    @abstractmethod
    def search_items_skus(self, list_of_skus: list[str]) -> dict[str, int]:
        """Return stock by exact SKU; include known zero-stock items, omit unknowns."""
        raise NotImplementedError

    @abstractmethod
    def analyse_items_used(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        **filters: Any,
    ) -> pd.DataFrame:
        """Return daily invoice quantities with SKU, Name, SoldAmount, Dates columns."""
        raise NotImplementedError

    @abstractmethod
    def search_inventory(
        self,
        *,
        sku: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        ram_capacity: int | None = None,
        ram_ddr: int | None = None,
        ram_speed: int | None = None,
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: str | None = None,
        hdd_capacity: int | None = None,
        hdd_type: Literal["HDD", "SSD"] | None = None,
        case_manufacturer: str | None = None,
        case_model: str | None = None,
        gpu_manufacturer: Literal["NVIDIA", "AMD"] | None = None,
        gpu_series: Literal["GeForce", "Radeon", "Quadro", "Nvidia"] | None = None,
        gpu_model: str | None = None,
        gpu_vram: int | None = None,
    ) -> list[ItemsSearchResponse]:
        raise NotImplementedError

    @abstractmethod
    def get_components_forecast(
        self,
        weeks: int = 1,
    ) -> list[ComponentForecast]:
        raise NotImplementedError
