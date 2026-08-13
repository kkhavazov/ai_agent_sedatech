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
            "Item category code. Always use the abbreviated code. "
            "Codes: FA=fan, GC=graphics card, CP=CPU, TW=case, "
            "ME=RAM, HD=storage, MB=motherboard."
        ),
        min_length=1,
        max_length=100,
    )
    ram_capacity: int | None = Field(
        default=None,
        description=(
            "RAM capacity in GB, for example 16 or 32. "
            "This automatically selects category ME (RAM)."
        ),
        gt=0,
    )
    ram_ddr: int | None = Field(
        default=None,
        description=(
            "RAM DDR generation as a number, for example 4 or 5. "
            "This automatically selects category ME (RAM)."
        ),
        ge=1,
        le=5,
    )

    @model_validator(mode="after")
    def validate_and_normalize_filters(self) -> "SearchItemsArguments":
        if self.category is not None:
            self.category = self.category.strip().upper()

        if self.ram_capacity is not None or self.ram_ddr is not None:
            if self.category is None:
                self.category = "ME"
            elif self.category != "ME":
                raise ValueError(
                    "ram_capacity and ram_ddr can only be used with RAM."
                )

        if not any(
            (
                self.sku,
                self.item_name,
                self.manufacturer,
                self.category,
                self.ram_capacity,
                self.ram_ddr,
            )
        ):
            raise ValueError("At least one item filter must be provided.")
        return self


def create_search_items_handler(item_service: ItemService):
    def search_items_handler(
        *,
        sku: str | None = None,
        manufacturer: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        ram_capacity: int | None = None,
        ram_ddr: int | None = None,
    ) -> dict[str, Any]:
        result = item_service.search_items(
            sku=sku,
            manufacturer=manufacturer,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
        )
        return {
            "requested_filters": {
                "sku": sku,
                "manufacturer": manufacturer,
                "category": category,
                "item_name": item_name,
                "ram_capacity": ram_capacity,
                "ram_ddr": ram_ddr,
            },
            "amount": result,
        }

    return search_items_handler
