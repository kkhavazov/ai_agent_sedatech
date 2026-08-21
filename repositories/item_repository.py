from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from models.item import ItemsSearchResponse

class ItemRepository(ABC):
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
    ) -> ItemsSearchResponse:
        raise NotImplementedError
