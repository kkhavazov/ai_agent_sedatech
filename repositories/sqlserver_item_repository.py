from __future__ import annotations

import logging
from typing import Any

import pymssql

from models.item import SearchItemResponse
from models.order import OrderItem
from repositories.item_repository import ItemRepository


logger = logging.getLogger(__name__)


class SqlServerItemRepository(ItemRepository):
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
        self.server = server
        self.user = user
        self.password = password
        self.database = database
        self.tds_version = tds_version
        self.port = port
        self.login_timeout_seconds = login_timeout_seconds
        self.query_timeout_seconds = query_timeout_seconds

    def _connect(self) -> pymssql.Connection:
        return pymssql.connect(
            server=self.server,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            tds_version=self.tds_version,
            charset="UTF-8",
            as_dict=True,
            appname="SedatechAIAgent",
            autocommit=True,
            login_timeout=self.login_timeout_seconds,
            timeout=self.query_timeout_seconds,
        )

    def search_inventory(
        self,
        *,
        sku: str | None = None,
        manufacturer: str | None = None,
        category: str | None = None,
        item_name: str | None = None,
        limit: int = 20,
    ) -> SearchItemResponse:
        safe_limit = max(1, min(int(limit), 100))
        filters: list[str] = []
        parameters: list[Any] = []

        for value, column in (
            (sku, "SERIE.Artikelnummer"),
            (manufacturer, "ART._HERSTELLER"),
            (category, "ART.ArtikelGruppe"),
            (item_name, "ART.Bezeichnung"),
        ):
            if value:
                filters.append(f"{column} LIKE %s")
                parameters.append(f"%{value.strip()}%")

        where_sql = "WHERE " + " AND ".join(
            [
                "SERIE.SCTyp <> 'O'",
                "LAGERP.Bestand > 0",
                "LAGERP.AngelegtAm >= DATEADD(day, -5000, GETDATE())",
                *filters,
            ]
        )
        from_sql = """
            FROM dbo.LAGERP
            INNER JOIN SERIE ON SERIE.Id = LAGERP.IdSerie
            INNER JOIN ART ON ART.Artikelnummer = SERIE.Artikelnummer
        """
        item_query = f"""
            SELECT TOP {safe_limit}
                SERIE.Artikelnummer AS SKU,
                ART.Bezeichnung AS ItemName,
                LAGERP.Menge AS Quantity,
                LAGERP.Wert AS Price
            {from_sql}
            {where_sql}
            ORDER BY LAGERP.AngelegtAm DESC
        """
        count_query = f"""
            SELECT COUNT(*) AS ItemCount
            {from_sql}
            {where_sql}
        """

        connection = None
        cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(item_query, tuple(parameters))
            rows: list[dict[str, Any]] = cursor.fetchall()
            cursor.execute(count_query, tuple(parameters))
            count_row = cursor.fetchone()
        except pymssql.Error as exc:
            logger.exception("Inventory search failed")
            raise RuntimeError(
                f"DATABASE_QUERY_ERROR: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

        return SearchItemResponse(
            total_count=int(count_row["ItemCount"]) if count_row else 0,
            items=[
                OrderItem(
                    sku=str(row["SKU"]).strip(),
                    name=str(row["ItemName"]).strip(),
                    quantity=int(row["Quantity"]),
                    price=(float(row["Price"]) if row.get("Price") is not None else None),
                )
                for row in rows
            ],
        )
