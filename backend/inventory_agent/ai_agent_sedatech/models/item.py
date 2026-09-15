from dataclasses import dataclass
from typing import TypedDict


ORDERED_AMOUNT_DESCRIPTION = (
    "Quantity ordered from suppliers for incoming inventory replenishment. "
    "This is not stock reserved for customers or customer demand. "
    "Do not subtract it from amount or count it as stock already received."
)


class MissingComponentEntry(TypedDict):
    ID: str
    count: int

@dataclass(slots=True)
class MissingComponent:
    order_number: str
    components: list[MissingComponentEntry]

@dataclass(slots=True)
class ItemsSearchResponse:
    sku: str
    name: str
    amount: int
    ordered: int  # Incoming supplier replenishment; see ORDERED_AMOUNT_DESCRIPTION.
    minimum_price: float
    maximum_price: float
    average_price: float


@dataclass(slots=True)
class ComponentForecast:
    sku: str
    name: str
    weekly_forecast: float
    stock_coverage: float
