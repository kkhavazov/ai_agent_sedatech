from __future__ import annotations

from abc import ABC, abstractmethod

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
    ) -> int:
        raise NotImplementedError
