from __future__ import annotations

import logging
from typing import Any, Literal

import pymssql

from repositories.item_repository import ItemRepository

from models.item import ItemsSearchResponse


logger = logging.getLogger(__name__)

case_inventory = {
    "Aerocool": [
        "P7-C1BG"
    ],
    "Akasa": [
        "Euler"
    ],
    "Antec": [
        "GX505"
    ],
    "Artic Cooling": [
        "Silentium Pro"
    ],
    "ASUS": [
        "ProArt PA401 Wood Edition TG Panel"
    ],
    "ATX": [
        "Open Chassis"
    ],
    "be quiet!": [
        "Light Base 500 LX Black",
        "Pure Base 500 White",
        "Pure Base 501 Airflow",
        "Pure Base 501 Black",
        "Pure Base 501 LX White",
        "Pure Base 600"
    ],
    "BitFenix": [
        "Nova TG",
        "Portal Windows"
    ],
    "Chieftec": [
        "BU-12B-300",
        "FI-01B-U3"
    ],
    "Compucase": [
        "8K01BS-SA120U"
    ],
    "CoolerMaster": [
        "CD600 Black",
        "Elite 302",
        "Elite 490",
        "Elite 681",
        "MasterBox 600",
        "MasterBox MB511 RGB",
        "MasterBox NR200-Black",
        "MasterBox NR200P-Cyan/Glass",
        "MasterBox NR200P-Orange/Gla",
        "MasterBox NR200P-Purple/Gl",
        "MasterBox NR200P-White",
        "MasterBox SL600M",
        "MasterCase H500P",
        "MasterFrame 600 Black",
        "Silencio S600 Metal"
    ],
    "Corsair": [
        "Carbide Air 540",
        "Obsidian 500D"
    ],
    "Cougar": [
        "QBX"
    ],
    "Deepcool": [
        "CC560 MESH V2",
        "CG530 4F",
        "CH260",
        "CH260 Wood",
        "CH270 Digital",
        "CH360 Digital",
        "CH510 Mesh Digital",
        "CH560 Digital",
        "CH690 Digital Black",
        "CH690 Digital White",
        "Genome Black/red V2",
        "GENOME III",
        "MATREXX 55 MESH V4 C",
        "MATREXX55 V3 White ADD-RGB 3F"
    ],
    "Fractal Design": [
        "Define C TG",
        "Define Nano S Mini-ITX",
        "North Chalk TG white",
        "North Charcoal TG Black",
        "North Momentum Black Edit",
        "Torrent Black TG Dark Tin",
        "Torrent Compact TG Light "
    ],
    "Fractal": [
        "North Meshify 3 XL Solid",
        "North XL Charcoal Black",
        "North XL Charcoal White"
    ],
    "GameMax": [
        "Contac COC Black/Grey"
    ],
    "HYTE": [
        "X50 Black",
        "X50 Snow White"
    ],
    "Jonsbo": [
        "T9 silver"
    ],
    "Kolink": [
        "Aviator Red Light",
        "KLA-002",
        "Punisher RGB"
    ],
    "LC-Power": [
        "lc-1340mi",
        "lc-1350mi"
    ],
    "Lian-Li": [
        "A3- Black",
        "A3- Black Wood Edition",
        "A3- White",
        "O11 Dynamic EVO",
        "PC-Q11B"
    ],
    "mITX": [
        "Newton UCFF (intel NUC)",
        "ST-F7CB EVO"
    ],
    "MSI": [
        "MAG FORGE M100R",
        "MAG PANO M100R PZ",
        "MPG GUNGNIR 110R",
        "MPG GUNGNIR 300R",
        "MPG GUNGNIR 300R White"
    ],
    "MS-TECH": [
        "CA-0280"
    ],
    "NZXT": [
        "H210i",
        "H510 Black",
        "H510 White",
        "Manta"
    ],
    "PHANTEKS": [
        "Evolv Series X2",
        "XT M3 RGB"
    ],
    "Q2": [
        "Illuminator blue"
    ],
    "Q-Bi": [
        "Platoon Leader"
    ],
    "RAIJINTEK": [
        "Arcadia III MS4"
    ],
    "Sharkoon": [
        "Shark Zone C10",
        "TG5 RGB",
        "TG6 RGB",
        "VG6-W Blue",
        "VS4-V"
    ],
    "Signum": [
        "SG1X TG RGB Black"
    ],
    "SilverStone": [
        "SST-ML08B"
    ],
    "Streacom": [
        "ST-F7C CB"
    ],
    "Zalman": [
        "I3 Neo ARGB Black",
        "I3 Neo Black",
        "I4 White",
        "P30 Black",
        "P30 Black&White",
        "P30 White",
        "P50 DS Black",
        "P50 DS White",
        "P60 Black",
        "Z1 Neo"
    ]
}


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
            # The same article filters occur in both grouped subqueries.
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
