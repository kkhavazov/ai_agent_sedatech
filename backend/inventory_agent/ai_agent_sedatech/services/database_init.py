from __future__ import annotations

import sqlite3
from pathlib import Path

from services.item_service import ItemService


def initialize_forecast_database(
    database_path: str | Path | None = None,
) -> Path:
    path = Path(database_path or Path(__file__).with_name("forecast.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        ItemService._initialize_forecast_database(connection)
    return path


if __name__ == "__main__":
    print(initialize_forecast_database())
