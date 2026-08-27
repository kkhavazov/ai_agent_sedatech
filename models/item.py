from dataclasses import dataclass
from typing import TypedDict


class MissingComponentEntry(TypedDict):
    ID: str
    count: int

@dataclass(slots=True)
class MissingComponent:
    order_number: str
    components: list[MissingComponentEntry]

@dataclass(slots=True)
class ItemsSearchResponse:
    name: str
    amount: int
    ordered: int
    minimum_price: float
    maximum_price: float
    average_price: float
