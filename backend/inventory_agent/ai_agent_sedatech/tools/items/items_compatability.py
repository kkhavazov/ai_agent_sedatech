from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from repositories.sqlserver_items_compatability_repository import (
    SqlServerItemsCompatabilityRepository,
    normalize_compatability_skus,
)
from tools.registry import ToolDefinition


class ItemsCompatabilityArguments(BaseModel):
    skus: list[str] = Field(min_length=1, description="Exact SKUs that must ALL occur in the same order.")
    sample_limit: int = Field(default=20, ge=0, le=100, description="Maximum example order numbers; zero returns only the count.")

    @field_validator("skus", mode="before")
    @classmethod
    def validate_skus(cls, value):
        return normalize_compatability_skus(value)


def build_items_compatability_tool(repository: SqlServerItemsCompatabilityRepository) -> ToolDefinition:
    return ToolDefinition(
        name="items_compatability",
        description=(
            "Count distinct orders containing ALL supplied exact SKUs together. "
            "Other items may also be present. Returns a total count and a bounded "
            "sample of order numbers; duplicate input SKUs and order rows count once. "
            "This is historical co-purchase evidence, not proof of technical compatibility."
        ),
        arguments_model=ItemsCompatabilityArguments,
        handler=repository.items_compatability,
    )
