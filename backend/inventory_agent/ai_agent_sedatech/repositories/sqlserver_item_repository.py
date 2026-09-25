from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

import pymssql

from repositories.item_repository import ItemRepository, normalize_skus

from models.item import ComponentForecast, ItemsSearchResponse

from tools.items.case_inventory import case_inventory as case_inventory

if TYPE_CHECKING:
    import pandas as pd

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

    def _build_article_filters(
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
    ) -> tuple[list[str], list[Any]]:
        filters: list[str] = []
        parameters: list[Any] = []

        for value, column in (
            (sku, "ART.Artikelnummer"),
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
        return filters, parameters

    def _build_inventory_query(self, filters: list[str]) -> str:
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
        return f"""
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
    def _build_analyze_components(self, filters: list[str]) -> str:
        where_sql = "WHERE " + " AND ".join(
            [
                "BELEGP.Belegtyp = 'R'",
                "ART.Artikelgruppe IN ('TW', 'GC', 'CP', 'NW', 'ME', 'HD', 'MB', 'PS', 'FA', 'OP')",
                *filters,
            ]
        )
        return f"""
        SELECT
            ART.Artikelnummer AS SKU,
            ART.Bezeichnung AS Name,
            SUM(BELEGP.Menge) AS SoldAmount,
            CAST(BELEGP.Datum AS date) AS Dates
        FROM dbo.BELEGP
        INNER JOIN dbo.ART
            ON BELEGP.Artikelnummer = ART.Artikelnummer
        {where_sql}
        GROUP BY ART.Artikelnummer, ART.Bezeichnung, CAST(BELEGP.Datum AS date)
        ORDER BY Dates, SKU
        """

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
        filters, parameters = self._build_article_filters(
            sku=sku,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
            ram_speed=ram_speed,
            cpu_manufacturer=cpu_manufacturer,
            cpu_generation=cpu_generation,
            cpu_model=cpu_model,
            hdd_capacity=hdd_capacity,
            hdd_type=hdd_type,
            case_manufacturer=case_manufacturer,
            case_model=case_model,
            gpu_manufacturer=gpu_manufacturer,
            gpu_series=gpu_series,
            gpu_model=gpu_model,
            gpu_vram=gpu_vram,
        )
        query = self._build_inventory_query(filters)

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

    def get_components_forecast(
        self,
        weeks: int = 1,
    ) -> list[ComponentForecast]:
        query = """
        WITH PopularComponents AS (
            SELECT
                BELEGP.Artikelnummer
            FROM dbo.BELEGP
            INNER JOIN dbo.ART
                ON BELEGP.Artikelnummer = ART.Artikelnummer
            WHERE
                BELEGP.Datum >= DATEADD(day, -84, GETDATE())
                AND ART.Artikelgruppe IN ('TW', 'GC', 'CP', 'NW', 'ME', 'HD', 'MB', 'PS', 'FA', 'OP')
                AND BELEGP.Belegtyp = 'R'
            GROUP BY
                BELEGP.Artikelnummer
            HAVING
                SUM(BELEGP.Menge) >= 2
            ), Usage AS (
            SELECT
                BELEGP.Artikelnummer,

                SUM(
                    CASE
                        WHEN BELEGP.Datum >= DATEADD(day, -28, GETDATE())
                        THEN BELEGP.Menge
                        ELSE 0
                    END
                ) AS UsageWeeks1To4,

                SUM(
                    CASE
                        WHEN BELEGP.Datum >= DATEADD(day, -56, GETDATE())
                        AND BELEGP.Datum < DATEADD(day, -28, GETDATE())
                        THEN BELEGP.Menge
                        ELSE 0
                    END
                ) AS UsageWeeks5To8,

                SUM(
                    CASE
                        WHEN BELEGP.Datum >= DATEADD(day, -84, GETDATE())
                        AND BELEGP.Datum < DATEADD(day, -56, GETDATE())
                        THEN BELEGP.Menge
                        ELSE 0
                    END
                ) AS UsageWeeks9To12

            FROM dbo.BELEGP

            INNER JOIN dbo.ART
                ON BELEGP.Artikelnummer = ART.Artikelnummer

            INNER JOIN PopularComponents
                ON BELEGP.Artikelnummer = PopularComponents.Artikelnummer

            WHERE
                BELEGP.Datum >= DATEADD(day, -84, GETDATE())
                AND BELEGP.Belegtyp = 'R'

            GROUP BY
                BELEGP.Artikelnummer
        ), Stock AS (
            SELECT
                SERIE.Artikelnummer,
                SUM(LAGERP.Bestand) AS CurrentStock
            FROM dbo.LAGERP

            INNER JOIN dbo.SERIE
                ON SERIE.Id = LAGERP.IdSerie

            INNER JOIN PopularComponents PC
                ON PC.Artikelnummer = SERIE.Artikelnummer

            GROUP BY
                SERIE.Artikelnummer
        ), Incoming AS (
            SELECT
                BELEGP.Artikelnummer,
                SUM(BELEGP.Menge) AS OrderedAmount
            FROM dbo.BELEG

            INNER JOIN dbo.BELEGP
                ON BELEGP.Belegnummer = BELEG.Belegnummer

            INNER JOIN PopularComponents PC
                ON PC.Artikelnummer = BELEGP.Artikelnummer

            WHERE
                BELEG.Belegtyp = 'B'
                AND BELEG.UebernahmeOffen < 0

            GROUP BY
                BELEGP.Artikelnummer
        )
            SELECT
            PC.Artikelnummer AS SKU,
            ART.Bezeichnung AS Name,

            COALESCE(S.CurrentStock, 0) AS CurrentStock,
            COALESCE(I.OrderedAmount, 0) AS OrderedAmount,

            COALESCE(U.UsageWeeks1To4, 0) AS UsageWeeks1To4,
            COALESCE(U.UsageWeeks5To8, 0) AS UsageWeeks5To8,
            COALESCE(U.UsageWeeks9To12, 0) AS UsageWeeks9To12

        FROM PopularComponents PC

        INNER JOIN dbo.ART
            ON ART.Artikelnummer = PC.Artikelnummer

        LEFT JOIN Stock S
            ON S.Artikelnummer = PC.Artikelnummer

        LEFT JOIN Incoming I
            ON I.Artikelnummer = PC.Artikelnummer

        LEFT JOIN Usage U
            ON U.Artikelnummer = PC.Artikelnummer

        ORDER BY
            ART.Bezeichnung;
"""
        
        connection = None
        cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query)
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
        result: list[ComponentForecast] = []
        for component in main_row:
            usage_1_4 = float(component["UsageWeeks1To4"] or 0)
            usage_5_8 = float(component["UsageWeeks5To8"] or 0)
            usage_9_12 = float(component["UsageWeeks9To12"] or 0)
            weekly_forecast = (
                (usage_1_4 / 4 * 0.50
                + usage_5_8 / 4 * 0.30
                + usage_9_12 / 4 * 0.20)*weeks
            )
            stock_coverage = (
                weekly_forecast
                - float(component["CurrentStock"] or 0)
                - float(component["OrderedAmount"] or 0)
            )
            if stock_coverage > 0:
                result.append(
                    ComponentForecast(
                        sku=str(component["SKU"]),
                        name=str(component["Name"]),
                        weekly_forecast=weekly_forecast,
                        stock_coverage=stock_coverage,
                    )
                )
        return result

    def search_items_skus(
        self,
        list_of_skus: list[str],
    ) -> dict[str, int]:
        list_of_skus = normalize_skus(list_of_skus)
        if not list_of_skus:
            return {}
        placeholders = ", ".join(["%s"] * len(list_of_skus))
        query = f"""
        SELECT
            ART.Artikelnummer, ART.Bezeichnung,
            COALESCE(SUM(LAGERP.Bestand), 0) AS CurrentStock
        FROM dbo.ART
        LEFT JOIN dbo.SERIE
            ON SERIE.Artikelnummer = ART.Artikelnummer
        LEFT JOIN dbo.LAGERP
            ON LAGERP.IdSerie = SERIE.Id
        WHERE ART.Artikelnummer IN ({placeholders})
        GROUP BY ART.Artikelnummer, ART.Bezeichnung
        """
        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, tuple(list_of_skus))
            rows = cursor.fetchall() or []

        except pymssql.Error as exc:
            raise RuntimeError(f"SQL Server query failed: {exc}") from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        stock = {
            str(row["Artikelnummer"]).strip().casefold(): int(row["CurrentStock"] or 0)
            for row in rows
        }
        # Preserve requested spelling even when SQL Server matches case-insensitively.
        # Known articles without stock return zero; unknown articles are omitted.
        return {
            sku: stock[sku.casefold()]
            for sku in list_of_skus
            if sku.casefold() in stock
        }

    def analyse_items_used(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
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
    ) -> pd.DataFrame:
        import pandas as pd

        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from cannot be later than date_to")
        filters, parameters = self._build_article_filters(
            sku=sku,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
            ram_speed=ram_speed,
            cpu_manufacturer=cpu_manufacturer,
            cpu_generation=cpu_generation,
            cpu_model=cpu_model,
            hdd_capacity=hdd_capacity,
            hdd_type=hdd_type,
            case_manufacturer=case_manufacturer,
            case_model=case_model,
            gpu_manufacturer=gpu_manufacturer,
            gpu_series=gpu_series,
            gpu_model=gpu_model,
            gpu_vram=gpu_vram,
        )
        if date_from is not None:
            filters.append("BELEGP.Datum >= %s")
            parameters.append(date_from)
        if date_to is not None:
            filters.append("BELEGP.Datum < DATEADD(day, 1, %s)")
            parameters.append(date_to)
        query = self._build_analyze_components(filters=filters)
        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, tuple(parameters))
            rows = cursor.fetchall() or []
            return pd.DataFrame.from_records(
                rows, columns=["SKU", "Name", "SoldAmount", "Dates"],
            )
        except pymssql.Error as exc:
            raise RuntimeError(
                f"SQL Server component sales query failed: {exc}"
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
