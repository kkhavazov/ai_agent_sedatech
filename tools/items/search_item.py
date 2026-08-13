from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from services.item_service import ItemService

ManufacturerType = Literal["Intel", "AMD"]

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
            "Manufacturer of the CPU, Intel or AMD."
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
    cpu_model: int | str | None = Field(
        default=None,
        description=(
            "Numeric CPU model. A suffix may also be attached and will be split out. "
            "Examples: 14900 or 14900KF; for i9-14900KF use cpu_model=14900 "
            "and cpu_prefix='KF', or pass cpu_model='14900KF'."
        ),
    )
    cpu_prefix: str | None = Field(
        default=None,
        description=(
            "CPU model suffix (despite the legacy field name). "
            "Preserve the complete suffix in its original order: i9-14900K uses K, "
            "i9-14900KF uses KF (not F or FK). For AMD use X, X3D, etc."
        ),
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
        if any(
            value is not None
            for value in (
                self.cpu_manufacturer,
                self.cpu_generation,
                self.cpu_model,
                self.cpu_prefix,
            )
        ):
            if self.category is None:
                self.category = "CP"
            elif self.category != "CP":
                raise ValueError(
                    "cpu_manufacturer, cpu_generation, cpu_model, and cpu_prefix can only be used with CPU."
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
                self.cpu_prefix,
            )
        ):
            raise ValueError("At least one item filter must be provided.")

        # Normalize a combined model and suffix such as 9900X or 7800X3D.
        if self.cpu_model is not None:
            model_str = str(self.cpu_model).strip()
            m = re.fullmatch(r"(\d+)([A-Za-z][A-Za-z0-9]*)?", model_str)
            if not m:
                raise ValueError(
                    "cpu_model must contain digits, optionally followed by a suffix like X, X3D, or K"
                )

            numeric_model, suffix = m.group(1), m.group(2)
            parsed_suffix = suffix.upper() if suffix else ""
            explicit_suffix = (self.cpu_prefix or "").strip().upper()
            if explicit_suffix and not re.fullmatch(r"[A-Z][A-Z0-9]*", explicit_suffix):
                raise ValueError("cpu_prefix must contain letters and digits only")
            if parsed_suffix and explicit_suffix and parsed_suffix != explicit_suffix:
                raise ValueError("cpu_model suffix conflicts with cpu_prefix")
            self.cpu_model = int(numeric_model)
            if self.cpu_model <= 0:
                raise ValueError("cpu_model must be greater than zero")
            self.cpu_prefix = explicit_suffix or parsed_suffix

            if self.cpu_manufacturer is None:
                raise ValueError("cpu_manufacturer is required when cpu_model is provided")
            if self.cpu_generation is None:
                raise ValueError("cpu_generation is required when cpu_model is provided")
        elif self.cpu_prefix is not None:
            if self.cpu_prefix.strip():
                raise ValueError("cpu_prefix requires cpu_model")
            self.cpu_prefix = None

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
        cpu_model: int | str | None = None,
        cpu_prefix: str | None = None,
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
            cpu_prefix=cpu_prefix,
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
            cpu_prefix=args.cpu_prefix,
            cpu_model=args.cpu_model,
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
                "cpu_prefix": args.cpu_prefix,
            },
            "amount": result,
        }

    return search_items_handler
