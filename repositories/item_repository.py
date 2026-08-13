from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

class ItemRepository(ABC):
    @abstractmethod
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
        cpu_model: str | None = None,
    ) -> int:
        raise NotImplementedError
