from models.item import SearchItemResponse
from models.order import OrderItem
from services.item_service import ItemService
from tools.items.search_item import create_search_items_handler


class StubItemRepository:
    def search_inventory(self, **filters):
        return SearchItemResponse(
            total_count=2,
            items=[OrderItem(sku="CP1", name="CPU", quantity=3, price=10.0)],
        )


def test_search_item_handler_returns_inventory_fields() -> None:
    handler = create_search_items_handler(ItemService(StubItemRepository()))
    result = handler(sku="CP", limit=1)

    assert result["total_count"] == 2
    assert result["possibly_truncated"] is True
    assert result["items"] == [
        {"sku": "CP1", "name": "CPU", "quantity": 3, "price": 10.0}
    ]
