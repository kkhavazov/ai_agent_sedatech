from __future__ import annotations

from abc import ABC, abstractmethod

from models.item import MissingComponent


class MissingRepository(ABC):
    @abstractmethod
    def find_missing_components(
        self,
        order_number: str,
    ) -> list[MissingComponent] | None:
        raise NotImplementedError

    @abstractmethod
    def find_missing_components_for_open_orders(
        self,
    ) -> list[MissingComponent] | None:
        raise NotImplementedError
