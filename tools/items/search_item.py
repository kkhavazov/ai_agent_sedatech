from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from repositories.sqlserver_item_repository import case_inventory
from services.item_service import ItemService

ManufacturerType = Literal["Intel", "AMD"]
StorageType = Literal["SSD", "HDD"]

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
    cpu_manufacturer: ManufacturerType | None = Field(
        default=None,
        description=(
            "Manufacturer of the CPU, 'Intel' or 'AMD'."
        ),
        min_length=1,
        max_length=100,
    )
    cpu_generation: int | None = Field(
        default=None,
        description=(
            "CPU product tier, not the processor-series generation. "
            "Use 9 for AMD Ryzen 9 9900X and 9 for Intel Core i9-14900K."
        ),
    )
    cpu_model: str | int | None = Field(
        default=None,
        description=(
            "CPU model including its complete suffix. Do not include the tier or "
            "manufacturer. Examples: 14900K, 14900KF, 9900X, or 7800X3D. "
            "ALWAYS use exact model name, not a partial name. "
        ),
    )
    hdd_type: StorageType | None = Field(
        default=None,
        description=(
            "Type of the storage, 'SSD' or 'HDD'."
        ),
        min_length=1,
        max_length=100,
    )
    hdd_capacity: int | None = Field(
        default=None,
        description=(
            "SSD capacity in GB, for example 1000 or 2000 etc. "
            "Round all the numbers, for example 2tb = 2000Gb"
            "This automatically selects category HD (SSDs and Hard Drives)."
        ),
    )
    case_manufacturer: str | None = Field(
        default=None,
        description=(
            "Case manufacturer from the available inventory, for example "
            "CoolerMaster, Corsair, or Fractal Design. This automatically "
            "selects category TW (case)."
        ),
        min_length=1,
        max_length=100,
    )
    case_model: str | None = Field(
        default=None,
        description=(
            "Exact case model from the available inventory, without the "
            "manufacturer; for example Elite 302. case_manufacturer is required."
        ),
        min_length=1,
        max_length=100,
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
        if self.hdd_capacity is not None or self.hdd_type is not None:
            if self.category is None:
                self.category = "HD"
            elif self.category != "HD":
                raise ValueError(
                    "hdd_capacity and hdd_type can only be used with Hard drives and SSDs."
                )
        if any(
            value is not None
            for value in (
                self.cpu_manufacturer,
                self.cpu_generation,
                self.cpu_model,
            )
        ):
            if self.category is None:
                self.category = "CP"
            elif self.category != "CP":
                raise ValueError(
                    "cpu_manufacturer, cpu_generation, cpu_model can only be used with CPU."
                )
        if self.case_manufacturer is not None or self.case_model is not None:
            if self.category is None:
                self.category = "TW"
            elif self.category != "TW":
                raise ValueError(
                    "case_manufacturer and case_model can only be used with cases."
                )
        if not any(
            (
                self.sku,
                self.item_name,
                self.manufacturer,
                self.category,
                self.ram_capacity,
                self.ram_ddr,
                self.cpu_manufacturer,
                self.cpu_generation,
                self.cpu_model,
                self.hdd_capacity,
                self.hdd_type,
                self.case_manufacturer,
                self.case_model,
            )
        ):
            raise ValueError("At least one item filter must be provided.")

        if self.case_model is not None and self.case_manufacturer is None:
            raise ValueError(
                "case_manufacturer is required when case_model is provided"
            )
        if self.case_manufacturer is not None:
            requested_manufacturer = self.case_manufacturer.strip().casefold()
            manufacturer = next(
                (
                    available
                    for available in case_inventory
                    if available.casefold() == requested_manufacturer
                ),
                None,
            )
            if manufacturer is None:
                raise ValueError("case_manufacturer is not in case_inventory")
            self.case_manufacturer = manufacturer

            if self.case_model is not None:
                requested_model = self.case_model.strip().casefold()
                model = next(
                    (
                        available.strip()
                        for available in case_inventory[manufacturer]
                        if available.strip().casefold() == requested_model
                    ),
                    None,
                )
                if model is None:
                    raise ValueError(
                        "case_model is not available for case_manufacturer"
                    )
                self.case_model = model

        if self.cpu_model is not None:
            if self.cpu_manufacturer is None:
                raise ValueError("cpu_manufacturer is required when cpu_model is provided")
            model = str(self.cpu_model).strip().upper()
            if not re.fullmatch(r"\d+[A-Z][A-Z0-9]*|\d+", model):
                raise ValueError(
                    "cpu_model must be an exact model such as 14900KF or 7800X3D"
                )
            if int(re.match(r"\d+", model).group()) <= 0:
                raise ValueError("cpu_model must be greater than zero")
            self.cpu_model = model

        if self.cpu_generation is not None and self.cpu_generation <= 0:
            raise ValueError("cpu_generation must be greater than zero")
        if self.cpu_generation is not None and self.cpu_manufacturer is None:
            raise ValueError(
                "cpu_manufacturer is required when cpu_generation is provided"
            )
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
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: str | int | None = None,
        hdd_capacity: int | None = None,
        hdd_type: Literal["HDD", "SSD"] | None = None,
        case_manufacturer: str | None = None,
        case_model: str | None = None,
    ) -> dict[str, Any]:
        # Validate and normalize inputs using SearchItemsArguments
        args = SearchItemsArguments(
            sku=sku,
            manufacturer=manufacturer,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
            cpu_generation=cpu_generation,
            cpu_manufacturer=cpu_manufacturer,
            cpu_model=cpu_model,
            hdd_capacity=hdd_capacity,
            hdd_type=hdd_type,
            case_manufacturer=case_manufacturer,
            case_model=case_model,
        )


        result = item_service.search_items(
            sku=args.sku,
            manufacturer=args.manufacturer,
            category=args.category,
            item_name=args.item_name,
            ram_capacity=args.ram_capacity,
            ram_ddr=args.ram_ddr,
            cpu_generation=args.cpu_generation,
            cpu_manufacturer=args.cpu_manufacturer,
            cpu_model=args.cpu_model,
            hdd_capacity=args.hdd_capacity,
            hdd_type=args.hdd_type,
            case_manufacturer=args.case_manufacturer,
            case_model=args.case_model,
        )
        return {
            "requested_filters": {
                "sku": args.sku,
                "manufacturer": args.manufacturer,
                "category": args.category,
                "item_name": args.item_name,
                "ram_capacity": args.ram_capacity,
                "ram_ddr": args.ram_ddr,
                "cpu_generation": args.cpu_generation,
                "cpu_manufacturer": args.cpu_manufacturer,
                "cpu_model": args.cpu_model,
                "hdd_capacity": args.hdd_capacity,
                "hdd_type": args.hdd_type,
                "case_manufacturer": args.case_manufacturer,
                "case_model": args.case_model,
            },
            "amount": result,
        }

    return search_items_handler
