from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from services.item_service import ItemService


class SearchItemsArguments(BaseModel):
    sku: str | None = Field(
        default=None,
        description="Full or partial item SKU, for example CP00000.",
        min_length=1,
        max_length=100,
    )
    item_name: str | None = Field(
        default=None,
        description="Full or partial item name.",
        min_length=1,
        max_length=100,
    )
    manufacturer: str | None = Field(
        default=None,
        description="Full or partial manufacturer name, for example Intel or AMD.",
        min_length=1,
        max_length=100,
    )
    category: str | None = Field(
        default=None,
        description=(
            "Item category code: FA=fan, GC=graphics card, CP=CPU, TW=case, "
            "ME=RAM, HD=storage, MB=motherboard."
        ),
        min_length=1,
        max_length=100,
    )
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def require_at_least_one_filter(self) -> "SearchItemsArguments":
        if not any((self.sku, self.item_name, self.manufacturer, self.category)):
            raise ValueError("At least one item filter must be provided.")
        return self


def create_search_items_handler(item_service: ItemService):
    def search_items_handler(
        *,
        sku: str | None = None,
        manufacturer: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        result = item_service.search_items(
            sku=sku,
            manufacturer=manufacturer,
            category=category,
            item_name=item_name,
            limit=limit,
        )
        returned_count = len(result.items)
        return {
            "returned_count": returned_count,
            "requested_limit": limit,
            "possibly_truncated": result.total_count > returned_count,
            "requested_filters": {
                "sku": sku,
                "manufacturer": manufacturer,
                "category": category,
                "item_name": item_name,
            },
            "total_count": result.total_count,
            "items": [
                {
                    "sku": item.sku,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                }
                for item in result.items
            ],
        }

    return search_items_handler
