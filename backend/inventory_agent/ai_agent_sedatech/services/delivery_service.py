from __future__ import annotations

from datetime import date

import pandas as pd

from repositories.delivery_repository import (
    DELIVERY_COLUMNS, DeliveryComponent, DeliveryRepository, DeliveryStatus,
)


class DeliveryService:
    def __init__(self, repository: DeliveryRepository | None = None) -> None:
        self.repository = repository

    def analyze_deliveries(
        self,
        *,
        components: list[DeliveryComponent],
        date_from: date | None,
        date_to: date | None,
        provider: str | None,
        status: DeliveryStatus | None,
        limit: int,
    ) -> tuple[pd.DataFrame, bool]:
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from cannot be later than date_to")
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        if status not in (None, "received", "waiting"):
            raise ValueError("status must be received or waiting")
        if self.repository is None:
            raise NotImplementedError("No incoming-delivery repository is configured.")
        frame = self.repository.analyze_deliveries_data(
            components=components, date_from=date_from, date_to=date_to,
            provider=provider, status=status, max_rows=limit + 1,
        )
        missing = set(DELIVERY_COLUMNS) - set(frame.columns)
        if missing:
            raise ValueError(f"Delivery data is missing columns: {', '.join(sorted(missing))}")
        if not frame["status"].isin(["received", "waiting"]).all():
            raise ValueError("Delivery data must use received/waiting statuses")
        result = frame.loc[:, DELIVERY_COLUMNS].head(limit).copy()
        result["quantity"] = pd.to_numeric(result["quantity"], errors="raise")
        for column in ("price_per_item", "price_overall"):
            result[column] = pd.to_numeric(result[column], errors="raise")
        return result, len(frame) > limit
