from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, field_validator

from services.item_service import ItemService


Sku = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SearchItemsSkusArguments(BaseModel):
    list_of_skus: list[Sku] = Field(
        min_length=1,
        max_length=500,
        description="Exact item SKUs whose current stock quantities are requested.",
    )

    @field_validator("list_of_skus")
    @classmethod
    def remove_duplicates(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


def create_search_items_skus_handler(item_service: ItemService):
    def handler(*, list_of_skus: list[str]) -> dict[str, Any]:
        args = SearchItemsSkusArguments(list_of_skus=list_of_skus)
        stock = item_service.search_items_skus(args.list_of_skus)
        return {
            "requested_skus": args.list_of_skus,
            "stock": stock,
            "missing_skus": [sku for sku in args.list_of_skus if sku not in stock],
        }

    return handler
