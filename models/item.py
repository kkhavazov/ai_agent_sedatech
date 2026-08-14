from dataclasses import dataclass

@dataclass(slots=True)
class MissingComponent:
    order_number: str
    component: str