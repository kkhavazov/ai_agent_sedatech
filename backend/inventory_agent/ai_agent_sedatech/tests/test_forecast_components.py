from datetime import datetime
from datetime import time
from zoneinfo import ZoneInfo

import pytest

from models.item import ComponentForecast
from services.item_service import ItemService
from services.forecast_worker import BERLIN_TIMEZONE, ForecastWorker
from tools.factory import build_tool_registry
from tools.items.forecast_components import (
    ForecastComponentsArguments,
    create_forecast_components_handler,
)


class ForecastRepository:
    def __init__(self) -> None:
        self.calls = 0

    def get_components_forecast(self, weeks: int = 1):
        self.calls += 1
        return [
            ComponentForecast(
                sku="CP00001",
                name="Test CPU",
                weekly_forecast=4.5 * weeks,
                stock_coverage=2.5 * weeks,
            )
        ]


class OrderService:
    pass


def test_service_calculates_and_caches_daily_forecast(tmp_path) -> None:
    repository = ForecastRepository()
    service = ItemService(repository, tmp_path / "forecast.db")
    now = datetime(2026, 9, 15, 9, tzinfo=ZoneInfo("Europe/Berlin"))

    first = service.forecast_components(weeks=2, now=now)
    second = service.forecast_components(weeks=2, now=now)

    assert first == second
    assert first[0].stock_coverage == 5.0
    assert repository.calls == 1


def test_force_refresh_recalculates_forecast(tmp_path) -> None:
    repository = ForecastRepository()
    service = ItemService(repository, tmp_path / "forecast.db")
    now = datetime(2026, 9, 15, 9, tzinfo=BERLIN_TIMEZONE)

    service.forecast_components(weeks=2, now=now)
    service.forecast_components(weeks=2, now=now, force=True)

    assert repository.calls == 2


def test_handler_returns_serializable_forecast(tmp_path) -> None:
    service = ItemService(ForecastRepository(), tmp_path / "forecast.db")

    result = create_forecast_components_handler(service)(weeks=3)

    assert result == {
        "weeks": 3,
        "count": 1,
        "components": [
            {
                "sku": "CP00001",
                "name": "Test CPU",
                "forecast_demand": 13.5,
                "suggested_order_quantity": 7.5,
            }
        ],
    }


@pytest.mark.parametrize("weeks", [0, 53])
def test_arguments_reject_invalid_week_ranges(weeks) -> None:
    with pytest.raises(ValueError):
        ForecastComponentsArguments(weeks=weeks)


def test_forecast_tool_is_registered(tmp_path) -> None:
    item_service = ItemService(ForecastRepository(), tmp_path / "forecast.db")
    registry = build_tool_registry(OrderService(), item_service)

    result = registry.execute("forecast_components", {"weeks": 2})

    assert result["success"] is True
    assert result["data"]["count"] == 1


class WorkerItemService:
    def __init__(self) -> None:
        self.calls = []

    def forecast_components(self, *, weeks: int, force: bool):
        self.calls.append({"weeks": weeks, "force": force})
        return []


def test_worker_run_once_forces_cache_refresh() -> None:
    service = WorkerItemService()
    worker = ForecastWorker(service, run_at=time(8, 0), weeks=4)

    worker.run_once()

    assert service.calls == [{"weeks": 4, "force": True}]


def test_worker_calculates_next_berlin_run() -> None:
    worker = ForecastWorker(WorkerItemService(), run_at=time(8, 0))

    before_run = datetime(2026, 9, 15, 7, 30, tzinfo=BERLIN_TIMEZONE)
    after_run = datetime(2026, 9, 15, 8, 30, tzinfo=BERLIN_TIMEZONE)

    assert worker.seconds_until_next_run(before_run) == 30 * 60
    assert worker.seconds_until_next_run(after_run) == 23.5 * 60 * 60
