import pytest

from repositories.demo_order_repository import DemoOrderRepository
from services.order_service import OrderNotFoundError, OrderService


def test_get_existing_order() -> None:
    service = OrderService(DemoOrderRepository())
    order = service.get_order("LS163908")
    print(order)
    assert order.status == 0

