from __future__ import annotations

from typing import Literal

from models.item import ItemsSearchResponse
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
        has_filter = any(
            [
                sku,
                category,
                item_name,
                ram_capacity,
                ram_ddr,
                ram_speed,
                cpu_generation,
                cpu_manufacturer,
                cpu_model,
                hdd_capacity,
                hdd_type,
                case_manufacturer,
                case_model,
                gpu_manufacturer,
                gpu_series,
                gpu_model,
                gpu_vram,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one item filter must be provided"
            )

        return self.repository.search_inventory(
            sku=sku,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
            ram_speed=ram_speed,
            cpu_generation = cpu_generation,
            cpu_manufacturer = cpu_manufacturer,
            cpu_model = cpu_model,
            hdd_capacity=hdd_capacity,
            hdd_type=hdd_type,
            case_manufacturer=case_manufacturer,
            case_model=case_model,
            gpu_manufacturer=gpu_manufacturer,
            gpu_series=gpu_series,
            gpu_model=gpu_model,
            gpu_vram=gpu_vram,
        )
