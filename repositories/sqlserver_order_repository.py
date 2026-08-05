from __future__ import annotations

import logging
from typing import Any

import pymssql

from models.order import Order, OrderItem
from repositories.order_repository import OrderRepository

from datetime import date
from typing import Any


logger = logging.getLogger(__name__)

class SqlServerOrderRepository:
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

    def find_by_order_number(self, order_number: str) -> Order | None:
        query = """
            SELECT TOP 1
                Belegnummer,
                Belegtyp,
                Status,
                Name,
                Vorname,
                Land
            FROM dbo.BELEG
            WHERE Belegnummer = %s
            ORDER BY Datum DESC
        """

        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, (order_number,))
            row = cursor.fetchone()

        except pymssql.Error as exc:
            raise RuntimeError(f"SQL Server query failed: {exc}") from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        if row is None:
            return None

        belegtyp = (
            str(row["Belegtyp"]).strip().upper()
            if row.get("Belegtyp") is not None
            else ""
        )

        allowed_item_types = {"A", "D", "L", "R"}

        items: list[OrderItem] = []

        if belegtyp in allowed_item_types:
            items = self.find_pc_config_by_order_number(order_number)

        first_name = (
            str(row["Vorname"]).strip()
            if row.get("Vorname") is not None
            else ""
        )

        last_name = (
            str(row["Name"]).strip()
            if row.get("Name") is not None
            else ""
        )

        customer_name = " ".join(
            part for part in [first_name, last_name] if part
        ) or None

        return Order(
            order_number=str(row["Belegnummer"]).strip(),
            document_type=belegtyp,
            status=(
                str(row["Status"]).strip()
                if row.get("Status") is not None
                else ""
            ),
            customer_name=customer_name,
            country=(
                str(row["Land"]).strip()
                if row.get("Land") is not None
                else None
            ),
            items=items,
        )
    def filter_orders(
        self,
        *,
        order_number: str | None = None,
        document_type: str | None = None,
        status: str | None = None,
        customer_name: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 200,
    ) -> list[Order]:

        safe_limit = max(1, min(int(limit), 100))

        where_clauses: list[str] = []
        parameters: list[Any] = []

        if order_number:
            where_clauses.append("Belegnummer LIKE %s")
            parameters.append(f"%{order_number.strip()}%")

        if status:
            where_clauses.append("Status = %s")
            parameters.append(status.strip())

        if document_type:
            where_clauses.append("Belegtyp = %s")
            parameters.append(document_type.strip().upper())

        if customer_name:
            normalized_name = customer_name.strip()

            where_clauses.append("""
                (
                    LTRIM(RTRIM(
                        ISNULL([Name], '') + ' ' + ISNULL([Vorname], '')
                    )) LIKE %s
                    OR
                    LTRIM(RTRIM(
                        ISNULL([Vorname], '') + ' ' + ISNULL([Name], '')
                    )) LIKE %s
                    OR [Name] LIKE %s
                    OR [Vorname] LIKE %s
                )
            """)

            name_pattern = f"%{normalized_name}%"

            parameters.extend([
                name_pattern,
                name_pattern,
                name_pattern,
                name_pattern,
            ])

        if date_from:
            where_clauses.append("Datum >= %s")
            parameters.append(date_from)

        if date_to:
            # This works if Datum is a DATE column.
            # See the datetime note below if Datum includes a time.
            where_clauses.append("Datum <= %s")
            parameters.append(date_to)

        where_sql = ""

        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = f"""
            SELECT TOP {safe_limit}
                Belegnummer AS OrderNumber,
                Belegtyp AS DocumentType,
                Status AS OrderStatus,
                LTRIM(RTRIM(
                    ISNULL([Name], '') + ' ' + ISNULL([Vorname], '')
                )) AS CustomerName,
                Land AS Country,
                Strasse AS Adress,
                BearbeitetAm AS OrderDate
            FROM dbo.BELEG
            {where_sql}
            ORDER BY BearbeitetAm DESC
        """

        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, tuple(parameters))

            rows: list[dict[str, Any]] = cursor.fetchall()

        except pymssql.Error as exc:
            logger.exception(
                "Order filter query failed. Filters=%r",
                {
                    "order_number": order_number,
                    "status": status,
                    "customer_name": customer_name,
                    "document_type": document_type,
                    "date_from": date_from,
                    "date_to": date_to,
                    "limit": safe_limit,
                },
            )

            raise RuntimeError(
                f"DATABASE_QUERY_ERROR: {type(exc).__name__}: {exc}"
            ) from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        return [
            Order(
                order_number=str(row["OrderNumber"]),
                document_type=str(row["DocumentType"]),
                status=str(row["OrderStatus"]),
                customer_name=(
                    str(row["CustomerName"])
                    if row.get("CustomerName") is not None
                    else None
                ),
                country=str(row["Country"]),
                adress=str(row["Adress"]),
                items=[],
            )
            for row in rows
        ]
    
    def find_pc_config_by_order_number(
        self,
        order_number: str,
    ) -> list[OrderItem]:
        query = """
            SELECT
                Artikelnummer,
                Bezeichnung,
                Menge,
                KalkpreisEuro,
                Stueckliste,
                Postext
            FROM dbo.BELEGP
            WHERE Belegnummer = %s
            ORDER BY Postext;
        """

        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, (order_number,))
            rows = cursor.fetchall()

        except pymssql.Error as exc:
            raise RuntimeError(
                f"SQL Server query failed while loading order items: {exc}"
            ) from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        if not rows:
            return []

        items: list[OrderItem] = []
        current_computer: OrderItem | None = None

        for row in rows:
            item_type = (
                str(row["Stueckliste"]).strip().upper()
                if row.get("Stueckliste") is not None
                else ""
            )

            item = OrderItem(
                sku=(
                    str(row["Artikelnummer"]).strip()
                    if row.get("Artikelnummer") is not None
                    else ""
                ),
                name=(
                    str(row["Bezeichnung"]).strip()
                    if row.get("Bezeichnung") is not None
                    else ""
                ),
                quantity=(
                    int(row["Menge"])
                    if row.get("Menge") is not None
                    else 0
                ),
                price=(
                    float(row["KalkpreisEuro"])
                    if row.get("KalkpreisEuro") is not None
                    else 0.0
                ),
                sub_items=[],
            )

            # H = main PC article
            if item_type == "H":
                current_computer = item
                items.append(current_computer)

            # K = component belonging to the current PC
            elif item_type == "K":
                if current_computer is None:
                    raise RuntimeError(
                        f"Component {item.sku!r} was found before its parent PC "
                        f"in order {order_number!r}."
                    )

                current_computer.sub_items.append(item)

            # Normal standalone article
            else:
                current_computer = None
                items.append(item)

        return items