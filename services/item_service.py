from __future__ import annotations

from typing import Literal

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
        ram_capacity: int | None = None,
        ram_ddr: int | None = None,
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: str | None = None,
    ) -> int:
        has_filter = any(
            [
                sku,
                manufacturer,
                category,
                item_name,
                ram_capacity,
                ram_ddr,
                cpu_generation,
                cpu_manufacturer,
                cpu_model,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one item filter must be provided"
            )

        return self.repository.search_inventory(
            sku=sku,
            manufacturer=manufacturer,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
            cpu_generation = cpu_generation,
            cpu_manufacturer = cpu_manufacturer,
            cpu_model = cpu_model,
        )
