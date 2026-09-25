from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from models.item import ComponentForecast, ItemsSearchResponse
from repositories.item_repository import ItemRepository, normalize_skus

class ItemNotFoundError(LookupError):
    pass

class ItemService:
    def __init__(
        self,
        repository: ItemRepository,
        forecast_database_path: str | Path | None = None,
    ) -> None:
        self.repository = repository
        self.forecast_database_path = Path(
            forecast_database_path
            or Path(__file__).with_name("forecast.db")
        )

    def search_items(
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
        gpu_series: Literal["GeForce", "Radeon", "Quadro", "Nvidia"] | None = None,
        gpu_model: str | None = None,
        gpu_vram: int | None = None,
    ) -> list[ItemsSearchResponse]:
        has_filter = any(
            [
                sku,
                category,
                item_name,
                ram_capacity,
                ram_ddr,
                ram_speed,
                cpu_generation,
                cpu_manufacturer,
                cpu_model,
                hdd_capacity,
                hdd_type,
                case_manufacturer,
                case_model,
                gpu_manufacturer,
                gpu_series,
                gpu_model,
                gpu_vram,
            ]
        )

        if not has_filter:
            raise ValueError(
                "At least one item filter must be provided"
            )

        return self.repository.search_inventory(
            sku=sku,
            category=category,
            item_name=item_name,
            ram_capacity=ram_capacity,
            ram_ddr=ram_ddr,
            ram_speed=ram_speed,
            cpu_generation = cpu_generation,
            cpu_manufacturer = cpu_manufacturer,
            cpu_model = cpu_model,
            hdd_capacity=hdd_capacity,
            hdd_type=hdd_type,
            case_manufacturer=case_manufacturer,
            case_model=case_model,
            gpu_manufacturer=gpu_manufacturer,
            gpu_series=gpu_series,
            gpu_model=gpu_model,
            gpu_vram=gpu_vram,
        )

    @staticmethod
    def _initialize_forecast_database(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS forecast_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                weeks INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS inventory_forecast (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                name TEXT NOT NULL,
                forecast_weekly REAL NOT NULL,
                stock_coverage REAL NOT NULL,
                FOREIGN KEY (run_id) REFERENCES forecast_runs(id)
            );
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(forecast_runs)")
        }
        if "weeks" not in columns:
            connection.execute(
                "ALTER TABLE forecast_runs "
                "ADD COLUMN weeks INTEGER NOT NULL DEFAULT 1"
            )

    @staticmethod
    def _load_cached_forecast(
        connection: sqlite3.Connection,
        *,
        created_on: str,
        weeks: int,
    ) -> list[ComponentForecast] | None:
        run = connection.execute(
            """
            SELECT id
            FROM forecast_runs
            WHERE substr(created_at, 1, 10) = ? AND weeks = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (created_on, weeks),
        ).fetchone()
        if run is None:
            return None

        rows = connection.execute(
            """
            SELECT sku, name, forecast_weekly, stock_coverage
            FROM inventory_forecast
            WHERE run_id = ?
            ORDER BY stock_coverage DESC, name
            """,
            (run[0],),
        ).fetchall()
        return [
            ComponentForecast(
                sku=str(row[0]),
                name=str(row[1]),
                weekly_forecast=float(row[2]),
                stock_coverage=float(row[3]),
            )
            for row in rows
        ]

    @staticmethod
    def _save_forecast(
        connection: sqlite3.Connection,
        forecast: list[ComponentForecast],
        *,
        created_at: datetime,
        weeks: int,
    ) -> None:
        cursor = connection.execute(
            "INSERT INTO forecast_runs (created_at, weeks) VALUES (?, ?)",
            (created_at.isoformat(), weeks),
        )
        run_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO inventory_forecast (
                run_id, sku, name, forecast_weekly, stock_coverage
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.sku,
                    item.name,
                    item.weekly_forecast,
                    item.stock_coverage,
                )
                for item in forecast
            ],
        )

    def search_items_skus(self, list_of_skus: list[str]) -> dict[str, int]:
        skus = normalize_skus(list_of_skus)
        if not skus:
            return {}
        return self.repository.search_items_skus(skus)

    def analyse_items_used(
        self,
        *,
        date_from: date,
        date_to: date,
        group_by: Literal["day", "week", "month", "year", "total"] = "month",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        if date_from is None or date_to is None:
            raise ValueError("date_from and date_to are required")
        if date_from > date_to:
            raise ValueError("date_from cannot be later than date_to")
        if group_by not in {"day", "week", "month", "year", "total"}:
            raise ValueError("group_by must be day, week, month, year, or total")
        if not any(value is not None and value != "" for value in filters.values()):
            raise ValueError("At least one item filter must be provided")
        frame = self.repository.analyse_items_used(
            date_from=date_from, date_to=date_to, **filters,
        )
        totals: dict[tuple[str, str, str | None], float] = {}
        for record in frame.to_dict(orient="records"):
            sold_on = record["Dates"]
            if isinstance(sold_on, datetime):
                sold_on = sold_on.date()
            elif isinstance(sold_on, str):
                sold_on = date.fromisoformat(sold_on)
            if group_by == "week":
                sold_on -= timedelta(days=sold_on.weekday())
            elif group_by == "month":
                sold_on = sold_on.replace(day=1)
            elif group_by == "year":
                sold_on = sold_on.replace(month=1, day=1)
            period = None if group_by == "total" else sold_on.isoformat()
            key = (str(record["SKU"]), str(record["Name"]), period)
            totals[key] = totals.get(key, 0.0) + float(record["SoldAmount"] or 0)
        return [
            {"sku": sku, "name": name, "period": period, "sold_amount": amount}
            for (sku, name, period), amount in sorted(
                totals.items(), key=lambda entry: (entry[0][2] or "", entry[0][0], entry[0][1]),
            )
        ]

    def forecast_components(
        self,
        weeks: int = 1,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> list[ComponentForecast]:
        if not 1 <= weeks <= 52:
            raise ValueError("weeks must be between 1 and 52")

        now = now or datetime.now(ZoneInfo("Europe/Berlin"))
        self.forecast_database_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.forecast_database_path) as connection:
            self._initialize_forecast_database(connection)
            if not force:
                cached = self._load_cached_forecast(
                    connection,
                    created_on=now.date().isoformat(),
                    weeks=weeks,
                )
                if cached is not None:
                    return cached

            forecast = self.repository.get_components_forecast(weeks=weeks)
            self._save_forecast(
                connection,
                forecast,
                created_at=now,
                weeks=weeks,
            )
            return forecast
