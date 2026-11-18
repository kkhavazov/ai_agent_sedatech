from __future__ import annotations

from pydantic import BaseModel, Field

from models.order import OrderItem
from services.order_service import OrderService
from tools.registry import ToolDefinition

from tools.orders.interpret_order_state import interpret_order_state


class GetOrderArguments(BaseModel):
    order_number: str = Field(
        min_length=1,
        max_length=50,
        description=(
            "The exact internal document number (Belegnummer), such as RA171165 "
            "(two letters followed by six digits). The input retains the name "
            "order_number for compatibility; pass document_number from tool results, "
            "not the external order_number or tracking_number. Use this lookup "
            "even when only the document ID is provided."
        ),
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
                "document_number": order_number,
                "message": "No order was found with this order number.",
            }

        interpreted_state = interpret_order_state(
            document_type=order.document_type,
            status=order.status,
        )

        return {
            "success": True,
            "found": True,
            "document_number": order.document_number,
            "order_number": order.order_number,
            "document_type": order.document_type,
            "status": order.status,
            **interpreted_state,
            "date": order.date,
            "date_created": order.date_created,
            "customer_name": order.customer_name,
            "country": order.country,
            "final_price": order.final_price,
            "tracking_number": order.tracking_number,
            "tax_number": order.tax_number,
            "company_name": order.company_name,
            "email": order.email,
            "phone_number": order.phone_number,
            "language": order.language,
            "platform": order.platform,
            "items": [
                serialize_item(item)
                for item in order.items
            ],
        }

    return ToolDefinition(
        name="get_order",
        description=(
            "Retrieve a customer sales order by its exact internal document number, including its current "
            "status, date, customer information, ordered computers, standalone items, "
            "and the components installed in each computer. Use this tool for an ID "
            "of two letters followed by six digits (e.g. RA171165), including a bare ID. "
            "document_number is the internal Belegnummer used for lookups and PC items. "
            "order_number is the external customer/platform order reference (IhrAuftrag), "
            "returned as text or null. It is not a document lookup key. "
            "tracking_number comes from _TRACKING and identifies a delivery for shipment tracking. "
            "tax_number is the VAT identification number (USt-IdNr.). "
            "platform is the sales channel the order came from, such as Amazon "
            "or the website, and is text or null when unknown. "
            "date_created is the creation date of the returned order/document; "
            "for document_type R it is the date it was sent. date is a legacy alias. "
            "This is not a confirmed delivery date. A tracking number alone does "
            "not establish delivery progress. "
            "tax_number, tracking_number, company_name, email, phone_number and "
            "language are text or null; preserve leading zeros and treat null as unknown."
        ),
        arguments_model=GetOrderArguments,
        handler=get_order,
    )
