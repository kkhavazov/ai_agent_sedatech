from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pymssql

from repositories.delivery_repository import DELIVERY_COLUMNS, DeliveryComponent, DeliveryStatus
from repositories.sqlserver_item_repository import SqlServerItemRepository


# Only generated predicates replace {filters}; all user values are bound via %s.
# BP.Datum is the supplier document date, not a promised or actual arrival date.
# NULL UebernahmeOffen cannot establish either status and is excluded.
ANALYZE_DELIVERIES_QUERY = """
SELECT TOP (%s)
    BP.Belegnummer AS delivery_number,
    BP.Artikelnummer AS component_sku,
    BP.Bezeichnung AS component_name,
    BP.EditMenge AS quantity,
    B.Name AS provider,
    BP.Datum AS delivery_date,
    BP.Einzelpreis AS price_per_item,
    BP.Gesamtpreis AS price_overall,
    CASE WHEN B.UebernahmeOffen < 0 THEN 'waiting'
         WHEN B.UebernahmeOffen >= 0 THEN 'received' END AS status
FROM BELEGP AS BP
LEFT JOIN BELEG AS B
    ON B.Belegnummer = BP.Belegnummer AND B.Belegtyp = BP.Belegtyp
LEFT JOIN ART ON ART.Artikelnummer = BP.Artikelnummer
WHERE BP.Belegtyp = 'B' AND BP.Zeilentyp = 'A'
    AND B.UebernahmeOffen IS NOT NULL
    {filters}
ORDER BY BP.Datum DESC, BP.Belegnummer, BP.Artikelnummer, BP.EditMenge
"""


class SqlServerDeliveryRepository:
    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        database: str,
        tds_version: str = "7.0",
        port: str = "1433",
        login_timeout_seconds: int = 10,
        query_timeout_seconds: int = 30,
    ) -> None:
        self.connection_options = dict(
            server=server, user=user, password=password, database=database,
            tds_version=tds_version, port=port, charset="UTF-8", as_dict=True,
            appname="SedatechAIAgent", autocommit=True,
            login_timeout=login_timeout_seconds, timeout=query_timeout_seconds,
        )

    def _connect(self):
        return pymssql.connect(**self.connection_options)

    @staticmethod
    def _build_component_filters(
        components: list[DeliveryComponent],
    ) -> tuple[list[str], list[Any]]:
        alternatives: list[str] = []
        parameters: list[Any] = []
        for component in components:
            arguments = {"sku": component} if isinstance(component, str) else component
            filters, values = SqlServerItemRepository._build_article_filters(**arguments)
            if not filters:
                raise ValueError("Each component must include an article filter")
            alternatives.append("(" + " AND ".join(filters) + ")")
            parameters.extend(values)
        filters = ["(" + " OR ".join(alternatives) + ")"] if alternatives else []
        return filters, parameters

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
        if not ANALYZE_DELIVERIES_QUERY.strip():
            raise NotImplementedError(
                "Delivery analysis SQL is not configured. Fill in "
                "ANALYZE_DELIVERIES_QUERY in sqlserver_delivery_repository.py."
            )
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from cannot be later than date_to")
        if not 1 <= max_rows <= 10001:
            raise ValueError("max_rows must be between 1 and 10001")
        if status not in (None, "received", "waiting"):
            raise ValueError("status must be received or waiting")
        filters, parameters = self._build_component_filters(components)
        if status == "waiting":
            filters.append("B.UebernahmeOffen < 0")
        elif status == "received":
            filters.append("B.UebernahmeOffen >= 0")
        if date_from is not None:
            filters.append("BP.Datum >= %s")
            parameters.append(date_from)
        if date_to is not None:
            filters.append("BP.Datum < DATEADD(day, 1, %s)")
            parameters.append(date_to)
        if provider is not None:
            filters.append("B.Name = %s")
            parameters.append(provider)
        query = ANALYZE_DELIVERIES_QUERY.format(
            filters="AND " + " AND ".join(filters) if filters else "",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple([max_rows, *parameters]))
                rows = cursor.fetchmany(max_rows)
        return pd.DataFrame.from_records(rows) if rows else pd.DataFrame(columns=DELIVERY_COLUMNS)
