from __future__ import annotations

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
            "components": [
                {
                    "sku": component.sku,
                    "name": component.name,
                    # The repository stores these under legacy internal names.
                    # Expose unambiguous names to the language model.
                    "forecast_demand": component.weekly_forecast,
                    "suggested_order_quantity": component.stock_coverage,
                }
                for component in components
            ],
        }

    return handler
