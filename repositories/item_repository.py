from __future__ import annotations

from abc import ABC, abstractmethod

from models.item import SearchItemResponse


class ItemRepository(ABC):
    @abstractmethod
    def search_inventory(
        self,
        *,
        sku: str | None = None,
        manufacturer: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        limit: int = 20,
    ) -> SearchItemResponse:
        raise NotImplementedError
