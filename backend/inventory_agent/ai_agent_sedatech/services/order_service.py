from __future__ import annotations

from datetime import date
from typing import Any, Literal

from models.order import Order
from repositories.order_repository import OrderRepository


class OrderNotFoundError(LookupError):
    pass


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    def get_order(self, order_number: str) -> Order:
        normalized = order_number.strip()
        if not normalized:
            raise ValueError("order_number cannot be empty")

        order = self.repository.find_by_order_number(normalized)
        if order is None:
            raise OrderNotFoundError(f"Order {normalized} was not found")
        return order

    from datetime import date


    def filter_orders(
        self,
        *,
        order_number: str | None = None,
        document_type: str | None = None,
        status: int | None = None,
        customer_name: str | None = None,
        country: str | None = None,
        address: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_order: Literal["newest", "oldest"] = "newest",
        limit: int = 20,
    ) -> list[Order]:
        if date_from and date_to and date_from > date_to:
            raise ValueError(
                "date_from cannot be later than date_to"
            )
        has_filter = any(
            [
                order_number,
                status,
                document_type,
                customer_name,
                sort_order,
                date_from,
                date_to,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one order filter must be provided"
            )

        safe_limit = max(1, min(limit, 100))

        return self.repository.filter_orders(
            order_number=order_number,
            document_type=document_type,
            status=status,
            customer_name=customer_name,
            date_from=date_from,
            date_to=date_to,
            sort_order=sort_order,
            limit=safe_limit,
        )
    def count_orders(
        self,
        *,
        document_type: str | None = None,
        status: int | None = None,
        country: str | None = None,
        address: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> int:
        if date_from and date_to and date_from > date_to:
            raise ValueError(
                "date_from cannot be later than date_to"
            )
        has_filter = any(
            [
                status,
                document_type,
                date_from,
                date_to,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one order filter must be provided"
            )


        return self.repository.count_orders(
            document_type=document_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

    def analyze_data(
        self,
        *,
        metrics: list[str],
        group_by: list[str],
        filters: dict[str, str | int | float | bool],
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: str | None = None,
        status: int | None = None,
        sort_by: str | None = None,
        sort_direction: Literal["asc", "desc"] = "asc",
        limit: int | None = None,
    ) -> Any:
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from cannot be later than date_to")
        frame = self.repository.analyze_orders_data(
            date_from=date_from,
            date_to=date_to,
            document_type=document_type,
            status=status,
            max_rows=10000,
        )
        import pandas as pd

        columns = {
            "platform": "Platform", "country": "Country", "city": "City",
            "postcode": "Postcode", "customer_number": "CustomerNumber",
            "document_type": "DocumentType", "status": "Status",
        }
        for key, value in filters.items():
            column = columns.get(key)
            if column is None:
                raise ValueError(f"Unsupported filter: {key}")
            frame = frame[frame[column] == value]

        dates = pd.to_datetime(frame["CreatedAt"], errors="coerce")
        if "year" in group_by:
            frame = frame.assign(year=dates.dt.year)
        if "month" in group_by:
            frame = frame.assign(month=dates.dt.month)
        if "day" in group_by:
            frame = frame.assign(day=dates.dt.strftime("%Y-%m-%d"))
        if "week" in group_by:
            week_start = dates - pd.to_timedelta(dates.dt.dayofweek, unit="D")
            frame = frame.assign(week=week_start.dt.strftime("%Y-%m-%d"))
        rename_groups = {key: columns[key] for key in group_by if key in columns}
        frame = frame.rename(columns={value: key for key, value in rename_groups.items()})

        aggregations: dict[str, tuple[str, str]] = {}
        if "revenue" in metrics:
            aggregations["revenue"] = ("FinalPrice", "sum")
        if "order_count" in metrics:
            aggregations["order_count"] = ("CreatedAt", "size")
        if "average_production_time" in metrics:
            if "ProductionTime" not in frame.columns:
                raise ValueError("average_production_time is not available in the order data source")
            aggregations["average_production_time"] = ("ProductionTime", "mean")

        if group_by:
            result = frame.groupby(group_by, dropna=False).agg(**aggregations).reset_index()
        else:
            values = {}
            for name, (column, operation) in aggregations.items():
                attribute = getattr(frame[column], operation)
                values[name] = attribute() if callable(attribute) else attribute
            result = pd.DataFrame([values])
        if sort_by:
            result = result.sort_values(sort_by, ascending=sort_direction == "asc")
        if limit is not None:
            result = result.head(limit)
        return result

    def analyze_orders_data(self, **arguments) -> Any:
        """Backward-compatible raw-data API."""
        return self.repository.analyze_orders_data(**arguments)
