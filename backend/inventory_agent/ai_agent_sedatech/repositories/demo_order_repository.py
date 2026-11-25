from __future__ import annotations

from datetime import date

from models.order import Order, OrderItem
from repositories.order_repository import OrderRepository


class DemoOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self._orders = {
            "LS163908": Order(
                document_number="LS163908",
                document_type="L",
                status=0,
                customer_name="Mauro Guagliardo",
                selling_price=1507.02,
                items=[
                    OrderItem(
                        sku="UCCZ604I1_13915",
                        name="Sedatech PC Gaming - Win 11",
                        quantity=1,
                        price=1507.02,
                        sub_items=[
                            OrderItem(
                                sku="UCCZ604I1_13915",
                        name="Sedatech PC Gaming - Win 11",
                        quantity=1,
                        price=1507.02,
                        sub_items=[]
                            )
                        ],
                    )
                ],
            )
        }

    def find_by_order_number(self, order_number: str) -> Order | None:
        return self._orders.get(order_number)

    from datetime import date

    def filter_orders(
        self,
        *,
        order_number: str | None = None,
        status: str | None = None,
        customer_name: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
    ) -> list[Order]:
        orders = list(self._orders.values())

        if order_number:
            search = order_number.casefold()
            orders = [
                order
                for order in orders
                if search in order.document_number.casefold()
            ]

        if status:
            search = status.casefold()
            orders = [
                order
                for order in orders
                if order.status.casefold() == search
            ]

        if customer_name:
            search = customer_name.casefold()
            orders = [
                order
                for order in orders
                if order.customer_name
                and search in order.customer_name.casefold()
            ]

        # Add date filtering when Order contains an order_date field.

        return orders[: max(1, min(limit, 100))]

    def analyze_orders_data(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: str | None = "R",
        status: int | None = None,
        max_rows: int = 10000,
    ):
        import pandas as pd

        rows = [
            {
                "CreatedAt": None,
                "CustomerNumber": None,
                "DocumentType": order.document_type,
                "Status": order.status,
                "Platform": "Demo",
                "selling_price": order.selling_price,
                "production_cost": order.production_cost,
                "gross_profit": order.gross_profit,
                "Taxes": None,
                "Country": None,
                "Postcode": None,
                "City": None,
            }
            for order in self._orders.values()
            if (document_type is None or order.document_type == document_type)
            and (status is None or order.status == status)
        ]
        columns = [
            "CreatedAt", "CustomerNumber", "DocumentType", "Status",
            "Platform", "selling_price", "production_cost", "gross_profit", "Taxes",
            "Country", "Postcode", "City",
        ]
        return pd.DataFrame.from_records(rows[:max_rows], columns=columns)
