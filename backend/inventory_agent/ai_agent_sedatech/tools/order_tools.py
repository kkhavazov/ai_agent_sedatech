from __future__ import annotations

from pydantic import BaseModel, Field

from services.order_service import OrderService
from tools.registry import ToolDefinition

from tools.orders.interpret_order_state import interpret_order_state


class GetOrderArguments(BaseModel):
    order_number: str = Field(
        min_length=1,
        max_length=50,
        description="The exact customer order number",
    )


def build_get_order_tool(service: OrderService) -> ToolDefinition:
    def serialize_item(item: OrderItem) -> dict:
        return {
            "sku": item.sku,
            "name": item.name,
            "quantity": item.quantity,
            "price": item.price,
            "components": [
                serialize_item(component)
                for component in item.sub_items
            ],
        }

    def get_order(order_number: str) -> dict:
        order = service.get_order(order_number)

        if order is None:
            return {
                "success": True,
                "found": False,
                "order_number": order_number,
                "message": "No order was found with this order number.",
            }

        interpreted_state = interpret_order_state(
            document_type=order.document_type,
            status=order.status,
        )

        return {
            "success": True,
            "found": True,
            "order_number": order.order_number,
            "document_type": order.document_type,
            "status": order.status,
            **interpreted_state,
            "date": order.date,
            "customer_name": order.customer_name,
            "country": order.country,
            "items": [
                serialize_item(item)
                for item in order.items
            ],
        }

    return ToolDefinition(
        name="get_order",
        description=(
            "Retrieve an order by its exact order number, including its current "
            "status, date, customer information, ordered computers, standalone items, "
            "and the components installed in each computer."
        ),
        arguments_model=GetOrderArguments,
        handler=get_order,
    )