from __future__ import annotations

import logging
from typing import Any, Literal

import pymssql

from repositories.item_repository import ItemRepository

from models.item import ItemsSearchResponse

from tools.items.case_inventory import case_inventory as case_inventory


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
        category: str | None = None,
        item_name: str | None = None,
        ram_capacity: int | None = None,
        ram_ddr: int | None = None,
        ram_speed: int | None = None,
        cpu_manufacturer: Literal["Intel", "AMD"] | None = None,
        cpu_generation: int | None = None,
        cpu_model: str | None = None,
        hdd_capacity: int | None = None,
        hdd_type: Literal["HDD", "SSD"] | None = None,
        case_manufacturer: str | None = None,
        case_model: str | None = None,
        gpu_manufacturer: Literal["NVIDIA", "AMD"] | None = None,
        gpu_series: Literal["Geforce", "Radeon", "Quadro", "Nvidia"] | None = None,
        gpu_model: str | None = None,
        gpu_vram: int | None = None,
    ) -> list[ItemsSearchResponse]:
        filters: list[str] = []
        parameters: list[Any] = []

        for value, column in (
            (sku, "SERIE.Artikelnummer"),
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
            if ram_speed is not None:
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append(f"%{ram_speed}%")
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
        if category == "HD":
            if hdd_type:
                if hdd_type == "HDD":
                    filters.append("ART.Bezeichnung LIKE %s")
                    if hdd_capacity:
                        parameters.append(f"{hdd_capacity}Gb HDD%")
                    else:
                        parameters.append(f"%HDD%")
                elif hdd_type == "SSD":
                    filters.append("ART.Bezeichnung LIKE %s")
                    if hdd_capacity:
                        parameters.append(f"{hdd_capacity}Gb SSD%")
                    else:
                        parameters.append(f"%SSD%")
        if category == "TW" and case_manufacturer:
            if case_model:
                full_name = f"{case_manufacturer} {case_model}"
                filters.append(
                    "(ART.Bezeichnung = %s OR ART.Bezeichnung LIKE %s)"
                )
                parameters.extend((full_name, f"{full_name} %"))
            else:
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append(f"{case_manufacturer} %")
        if category == "GC":
            if gpu_manufacturer:
                if gpu_manufacturer == "AMD":
                    filters.append("ART.Bezeichnung LIKE %s")
                    parameters.append("Radeon %")
                else:
                    filters.append(
                        "(ART.Bezeichnung LIKE %s OR ART.Bezeichnung LIKE %s "
                        "OR ART.Bezeichnung LIKE %s)"
                    )
                    parameters.extend(("Geforce %", "Quadro %", "Nvidia %"))
            if gpu_model:
                filters.append("ART.Bezeichnung LIKE %s")
                parameters.append(f"%{gpu_model}%")
            if gpu_vram:
                if gpu_vram > 2:
                    filters.append("ART.Bezeichnung LIKE %s")
                    parameters.append(f"%{gpu_vram}GB%")
                elif gpu_vram == 1:
                    filters.append("ART.Bezeichnung LIKE %s")
                    parameters.append(f"%1024MB%")
                else:
                    filters.append("ART.Bezeichnung LIKE %s")
                    parameters.append("%2048MB%")
        where_sql = "WHERE " + " AND ".join(
            [
                "SERIE.SCTyp <> 'O'",
                "LAGERP.Bestand > 0",
                "LAGERP.AngelegtAm >= DATEADD(day, -5000, GETDATE())",
                *filters,
            ]
        )
        where_sql_sum = "WHERE " + " AND ".join(
            [
                "BELEG.Belegtyp = 'B'",
                "BELEG.UebernahmeOffen < 0",
                "BELEGP.Artikelnummer IN ("
                "SELECT DISTINCT SERIE.Artikelnummer "
                "FROM dbo.LAGERP "
                "INNER JOIN SERIE ON SERIE.Id = LAGERP.IdSerie "
                "INNER JOIN ART ON ART.Artikelnummer = SERIE.Artikelnummer "
                "WHERE LAGERP.Wert <> 0"
                + (" AND " + " AND ".join(filters) if filters else "")
                + ")",
            ]
        )
        query = f"""
            SELECT
                Stock.Artikelnummer,
                Stock.Bezeichnung,
                Stock.ItemCount,
                Stock.MinimumPrice,
                Stock.MaximumPrice,
                Stock.AveragePrice,
                Orders.OrderedAmount
            FROM
            (
                SELECT
                    ART.Bezeichnung, ART.Artikelnummer,
                    COALESCE(SUM(LAGERP.Bestand), 0) AS ItemCount,
                    MIN(LAGERP.Wert) AS MinimumPrice,
                    MAX(LAGERP.Wert) AS MaximumPrice,
                    AVG(LAGERP.Wert) AS AveragePrice
                FROM dbo.LAGERP
                INNER JOIN SERIE
                    ON SERIE.Id = LAGERP.IdSerie
                INNER JOIN ART
                    ON ART.Artikelnummer = SERIE.Artikelnummer
                {where_sql}
                        GROUP BY ART.Bezeichnung, ART.Artikelnummer
            ) AS Stock

            LEFT JOIN
            (
                SELECT
                ART.Bezeichnung, ART.Artikelnummer,
                    COALESCE(SUM(BELEGP.Menge), 0) AS OrderedAmount
                FROM dbo.BELEG
                    INNER JOIN dbo.BELEGP
                        ON BELEGP.Belegnummer = BELEG.Belegnummer
                    INNER JOIN dbo.ART
                        ON ART.Artikelnummer = BELEGP.Artikelnummer
                {where_sql_sum}
                        GROUP BY ART.Bezeichnung, ART.Artikelnummer
            ) AS Orders
                ON Orders.Artikelnummer = Stock.Artikelnummer
                AND Orders.Bezeichnung = Stock.Bezeichnung

                ORDER BY Stock.Bezeichnung
        """

        connection = None
        cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, tuple(parameters + parameters))
            main_row = cursor.fetchall()
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

        
        result: list[ItemsSearchResponse] = []
        for item in main_row:
            total_amount = int(item["ItemCount"] or 0)
            ordered_amount = int(item["OrderedAmount"] or 0)

            result.append(ItemsSearchResponse(
                sku=str(item["Artikelnummer"]),
                name=str(item["Bezeichnung"]),
                amount=total_amount,
                ordered=ordered_amount,
                minimum_price=float(item["MinimumPrice"] or 0),
                maximum_price=float(item["MaximumPrice"] or 0),
                average_price=float(item["AveragePrice"] or 0),
            ))
        return result

    def get_popular_items(
        self, 
    ):
        
        
        connection = None
        cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, tuple(parameters + parameters))
            main_row = cursor.fetchall()
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
