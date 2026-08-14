from __future__ import annotations

import os
import re

import pymssql

from models.item import MissingComponent
from repositories.missing_repository import MissingRepository


class SqlServerMissingRepository(MissingRepository):
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

    def find_missing_components(
        self,
        order_number: str,
    ) -> list[MissingComponent] | None:
        query_items = """
            SELECT t1.Text AS NoteText
            FROM NOTIZ t1 WITH (NOLOCK)
            INNER JOIN Adress t2 WITH (NOLOCK)
                ON t1.Blobkey = t2.Adresstyp
            INNER JOIN BELEG t3 WITH (NOLOCK)
                ON t2.Name = t3.Name
            WHERE t3.Belegnummer = %s
        """
        query_order = """
            SELECT Artikelnummer
            FROM BELEGP
            WHERE Belegnummer = %s
            """
        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query_items, (order_number,))
            items_rows = cursor.fetchall()
            cursor.execute(query_order, (order_number,))
            order_items = {
                str(item["Artikelnummer"]).strip().upper()
                for item in cursor.fetchall()
                if item.get("Artikelnummer") is not None
            }

        except pymssql.Error as exc:
            raise RuntimeError(f"SQL Server query failed: {exc}") from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        if not items_rows:
            return None

        item_categories = {
            "CP", "ME", "MB", "BU", "FA", "GC", "HD", "TW", "PS",
            "MO", "ZZ", "SW", "TF", "OP", "OPD", "OPB", "NW",
        }
        result: list[MissingComponent] = []
        seen: set[str] = set()

        for row in items_rows:
            note_text = row.get("NoteText")
            if not isinstance(note_text, str) or not re.search(
                r"\bmissing\b", note_text, flags=re.IGNORECASE
            ):
                continue

            components = re.findall(
                r"\b[A-Za-z]{2,3}[A-Za-z0-9_-]*\b",
                note_text,
            )
            for component in components:
                normalized_component = component.upper()
                category = next(
                    (
                        candidate
                        for candidate in sorted(
                            item_categories,
                            key=len,
                            reverse=True,
                        )
                        if normalized_component.startswith(candidate)
                    ),
                    None,
                )
                if category and normalized_component not in seen:
                    seen.add(normalized_component)
                    if normalized_component not in order_items:
                        result.append(
                            MissingComponent(
                                order_number=order_number,
                                component=component,
                            )
                        )

        return result or None

    def find_missing_components_for_open_orders(
        self,
    ) -> list[MissingComponent] | None:
        query_open_orders = """
            SELECT Belegnummer
            FROM BELEG
            WHERE Adressnummer <> 'K10000' AND Adressnummer <> 'DE00000' AND Adressnummer <> 'K000000' AND Vorlage = '' 
            AND Belegtyp = 'L'
            AND Status = '0'
        """
        connection = None
        cursor = None
        missing_components_list: list[MissingComponent] = []

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query_open_orders)
            open_orders_rows = cursor.fetchall()

            for row in open_orders_rows:
                order_number = row.get("Belegnummer")
                if order_number:
                    missing_components = self.find_missing_components(order_number)
                    if missing_components:
                        missing_components_list.extend(missing_components)

        except pymssql.Error as exc:
            raise RuntimeError(f"SQL Server query failed: {exc}") from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        return missing_components_list or None

if __name__ == "__main__":
    sqlserver_server = os.getenv("SQLSERVER_SERVER") or None
    sqlserver_user = os.getenv("SQLSERVER_USER") or None
    sqlserver_password = os.getenv("SQLSERVER_PASSWORD") or None
    sqlserver_database = os.getenv("SQLSERVER_DATABASE") or None
    sqlserver_tds_version: str = os.getenv(
        "SQLSERVER_TDS_VERSION",
        "7.0",
    )
    sqlserver_port: str = os.getenv(
        "SQLSERVER_PORT",
        "1433",
    )
    required_settings = {
        "SQLSERVER_SERVER": sqlserver_server,
        "SQLSERVER_USER": sqlserver_user,
        "SQLSERVER_PASSWORD": sqlserver_password,
        "SQLSERVER_DATABASE": sqlserver_database,
    }
    missing_settings = [
        name for name, value in required_settings.items() if not value
    ]
    if missing_settings:
        raise RuntimeError(
            "Missing SQL Server environment variables: "
            + ", ".join(missing_settings)
        )

    repository = SqlServerMissingRepository(
        server=sqlserver_server or "",
        user=sqlserver_user or "",
        password=sqlserver_password or "",
        database=sqlserver_database or "",
        tds_version=sqlserver_tds_version,
        port=sqlserver_port,
    )
    order_number = "LS164014"
    missing_components = repository.find_missing_components_for_open_orders()
    print(missing_components)
