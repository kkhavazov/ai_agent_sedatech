import pytest
from pydantic import ValidationError

from services.item_service import ItemService
from tools.items.search_item import (
    SearchItemsArguments,
    create_search_items_handler,
)


class StubItemRepository:
    def __init__(self) -> None:
        self.filters = {}

    def search_inventory(self, **filters) -> int:
        self.filters = filters
        return 7


def test_search_item_handler_returns_amount() -> None:
    repository = StubItemRepository()
    handler = create_search_items_handler(ItemService(repository))

    result = handler(category="ME", ram_capacity=32)

    assert result["amount"] == 7
    assert result["requested_filters"]["ram_capacity"] == 32
    assert repository.filters["ram_capacity"] == 32


def test_ram_fields_infer_ram_category() -> None:
    arguments = SearchItemsArguments(ram_capacity=16, ram_ddr=4)

    assert arguments.category == "ME"


def test_ram_fields_reject_conflicting_category() -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(category="GC", ram_capacity=32)


def test_category_is_normalized() -> None:
    arguments = SearchItemsArguments(category=" me ")

    assert arguments.category == "ME"
