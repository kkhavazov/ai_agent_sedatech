from dataclasses import dataclass

@dataclass(slots=True)
class MissingComponent:
    order_number: str
    component: str

@dataclass(slots=True)
class ItemsSearchResponse:
    amount: int
    ordered: int
    minimum_price: float
    maximum_price: float
    average_price: float