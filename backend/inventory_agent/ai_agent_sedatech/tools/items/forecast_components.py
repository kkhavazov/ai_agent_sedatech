from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, Field

from services.item_service import ItemService


class ForecastComponentsArguments(BaseModel):
    weeks: int = Field(
        default=1,
        ge=1,
        le=52,
        description="Number of upcoming weeks to forecast.",
    )


def create_forecast_components_handler(item_service: ItemService):
    def handler(*, weeks: int = 1) -> dict[str, object]:
        components = item_service.forecast_components(weeks=weeks)
        return {
            "weeks": weeks,
            "count": len(components),
            "components": [asdict(component) for component in components],
        }

    return handler
