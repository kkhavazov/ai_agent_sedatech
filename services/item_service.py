from __future__ import annotations

from models.item import SearchItemResponse
from repositories.item_repository import ItemRepository

class ItemNotFoundError(LookupError):
    pass

class ItemService:
    def __init__(self, repository: ItemRepository) -> None:
        self.repository = repository

    def search_items(
        self,
        *,
        sku: str | None = None,
        manufacturer: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        limit: int = 20,
    ) -> SearchItemResponse:
        has_filter = any(
            [
                sku,
                manufacturer,
                category,
                item_name,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one item filter must be provided"
            )

        safe_limit = max(1, min(limit, 100))

        return self.repository.search_inventory(
            sku=sku,
            manufacturer=manufacturer,
            category=category,
            item_name=item_name,
            limit=safe_limit,
        )
