from __future__ import annotations

from datetime import date
from typing import Any, Literal, Protocol

import pandas as pd

DeliveryStatus = Literal["received", "waiting"]
DeliveryComponent = str | dict[str, Any]
DELIVERY_COLUMNS = [
    "delivery_number", "component_sku", "component_name", "provider",
    "delivery_date", "status", "quantity",
]


class DeliveryRepository(Protocol):
    def analyze_deliveries_data(
        self,
        *,
        components: list[DeliveryComponent],
        date_from: date | None,
        date_to: date | None,
        provider: str | None,
        status: DeliveryStatus | None,
        max_rows: int,
    ) -> pd.DataFrame:
        """Return incoming supplier lines using DELIVERY_COLUMNS, never sales.

        Components use the inventory article filters: strings are partial SKUs,
        dictionaries contain sku/category/item_name or hardware attributes.
        Match any component entry (AND within an entry); all other filters
        combine with AND. Empty components and None values mean no filter.
        Provider matches an exact supplier name. Dates are inclusive:
        delivery_date is BP.Datum (supplier document date), not the actual
        or expected arrival date. Undated rows are
        included only when no date bounds are requested.

        Status waiting means UebernahmeOffen < 0; received means
        UebernahmeOffen >= 0. NULL status values are excluded. Each row represents
        a delivery component line with BP.EditMenge as quantity; the document
        status does not establish a partially received quantity.
        Sort by delivery_date descending, delivery_number, component_sku,
        quantity before applying max_rows. Return the columns even
        when there are no matching rows.
        """
        ...
