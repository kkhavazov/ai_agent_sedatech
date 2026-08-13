from __future__ import annotations

import logging
from typing import Any, Literal

import pymssql

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
        ram_capacity: int | None = None,
        ram_ddr: int | None = None,
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: str | None = None,
    ) -> int:
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
        if category == "ME":
            if ram_capacity is not None:
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append(f"{ram_capacity}GB%")
            if ram_ddr is not None:
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append(f"%DDR{ram_ddr}%")
        if category == "CP" and cpu_manufacturer:
            gen = str(cpu_generation).strip() if cpu_generation is not None else ""
            model = str(cpu_model).strip() if cpu_model is not None else ""

            if model:
                if cpu_manufacturer == "Intel":
                    tier = gen or "%"
                    legacy_name = f"Intel Core i{tier}-{model}"
                    ultra_name = f"Intel Core Ultra {tier} {model}"
                    filters.append(
                        "(ART.Bezeichnung LIKE %s OR ART.Bezeichnung LIKE %s "
                        "OR ART.Bezeichnung LIKE %s OR ART.Bezeichnung LIKE %s)"
                    )
                    parameters.extend(
                        (
                            legacy_name,
                            f"{legacy_name} %",
                            ultra_name,
                            f"{ultra_name} %",
                        )
                    )
                elif cpu_manufacturer == "AMD":
                    full_name = f"AMD Ryzen {gen or '%'} {model}"
                    filters.append(
                        "(ART.Bezeichnung LIKE %s OR ART.Bezeichnung LIKE %s)"
                    )
                    parameters.extend((full_name, f"{full_name} %"))
            elif cpu_generation is not None:
                filters.append("ART.Bezeichnung LIKE %s")
                if cpu_manufacturer == "Intel":
                    parameters.append(f"Intel Core i{gen}-%")
                else:
                    parameters.append(f"AMD Ryzen {gen} %")
            elif cpu_manufacturer == "Intel":
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append(f"Intel Core %")
            else:
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append("AMD Ryzen %")
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
        count_query = f"""
            SELECT COALESCE(SUM(LAGERP.Bestand), 0) AS ItemCount
            {from_sql}
            {where_sql}
        """

        connection = None
        cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
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

        return int(count_row["ItemCount"]) if count_row else 0
