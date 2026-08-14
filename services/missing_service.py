from __future__ import annotations

from models.item import MissingComponent
from repositories.missing_repository import MissingRepository


class MissingComponentService:
    def __init__(self, repository: MissingRepository) -> None:
        self.repository = repository

    def find_for_order(self, order_number: str) -> list[MissingComponent]:
        normalized = order_number.strip()
        if not normalized:
            raise ValueError("order_number cannot be empty")
        return self.repository.find_missing_components(normalized) or []

    def find_for_open_orders(self) -> list[MissingComponent]:
        return self.repository.find_missing_components_for_open_orders() or []
