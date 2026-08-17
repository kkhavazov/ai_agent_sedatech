import pytest
from pydantic import ValidationError

from repositories.demo_item_repository import DemoItemRepository
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


def test_cpu_fields_infer_category_and_parse_model_suffix() -> None:
    arguments = SearchItemsArguments(
        cpu_manufacturer="AMD",
        cpu_generation=9,
        cpu_model="9900x",
    )

    assert arguments.category == "CP"
    assert arguments.cpu_model == "9900X"


def test_suffixless_cpu_model_is_supported() -> None:
    arguments = SearchItemsArguments(
        cpu_manufacturer="AMD",
        cpu_generation=7,
        cpu_model=7700,
    )

    assert arguments.cpu_model == "7700"


def test_cpu_fields_reject_conflicting_category() -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(category="GC", cpu_manufacturer="AMD")


def test_cpu_generation_requires_manufacturer() -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(cpu_generation=9)


@pytest.mark.parametrize("model", [0, -1])
def test_cpu_model_must_be_positive(model) -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(
            cpu_manufacturer="AMD",
            cpu_generation=9,
            cpu_model=model,
        )


def test_cpu_handler_forwards_normalized_filters() -> None:
    repository = StubItemRepository()
    handler = create_search_items_handler(ItemService(repository))

    result = handler(
        cpu_manufacturer="Intel",
        cpu_generation=9,
        cpu_model="14900kf",
    )

    assert repository.filters["category"] == "CP"
    assert repository.filters["cpu_manufacturer"] == "Intel"
    assert repository.filters["cpu_model"] == "14900KF"
    assert result["requested_filters"]["cpu_model"] == "14900KF"


def test_cpu_model_does_not_require_tier() -> None:
    arguments = SearchItemsArguments(
        cpu_manufacturer="Intel",
        cpu_model="14900KF",
    )

    assert arguments.category == "CP"
    assert arguments.cpu_generation is None
    assert arguments.cpu_model == "14900KF"


def test_demo_repository_accepts_cpu_filters() -> None:
    handler = create_search_items_handler(ItemService(DemoItemRepository()))

    result = handler(
        cpu_manufacturer="AMD",
        cpu_generation=9,
        cpu_model="9900X",
    )

    assert result["amount"] == 0


def test_case_fields_infer_category_and_normalize_inventory_names() -> None:
    arguments = SearchItemsArguments(
        case_manufacturer=" coolermaster ",
        case_model="elite 302",
    )

    assert arguments.category == "TW"
    assert arguments.case_manufacturer == "CoolerMaster"
    assert arguments.case_model == "Elite 302"


def test_case_model_requires_manufacturer() -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(case_model="Elite 302")


def test_case_model_must_belong_to_manufacturer() -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(
            case_manufacturer="Corsair",
            case_model="Elite 302",
        )


def test_case_fields_reject_conflicting_category() -> None:
    with pytest.raises(ValidationError):
        SearchItemsArguments(
            category="CP",
            case_manufacturer="CoolerMaster",
        )


def test_case_handler_forwards_normalized_filters() -> None:
    repository = StubItemRepository()
    handler = create_search_items_handler(ItemService(repository))

    result = handler(
        case_manufacturer="coolermaster",
        case_model="elite 302",
    )

    assert repository.filters["category"] == "TW"
    assert repository.filters["case_manufacturer"] == "CoolerMaster"
    assert repository.filters["case_model"] == "Elite 302"
    assert result["requested_filters"]["case_model"] == "Elite 302"
