from __future__ import annotations

from models.item import SearchItemResponse
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
        limit: int = 20,
    ) -> SearchItemResponse:
        items = self._items
        if sku:
            items = [item for item in items if sku.casefold() in item.sku.casefold()]
        if item_name:
            items = [item for item in items if item_name.casefold() in item.name.casefold()]
        if category:
            items = [item for item in items if item.sku.casefold().startswith(category.casefold())]
        if manufacturer:
            items = []
        return SearchItemResponse(total_count=len(items), items=items[:limit])
