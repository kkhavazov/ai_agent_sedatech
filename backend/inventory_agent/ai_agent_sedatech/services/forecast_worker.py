from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from config import Settings
from factory import build_item_repository
from services.item_service import ItemService


logger = logging.getLogger(__name__)
BERLIN_TIMEZONE = ZoneInfo("Europe/Berlin")


class ForecastWorker:
    def __init__(
        self,
        item_service: ItemService,
        *,
        run_at: time = time(8, 0),
        weeks: int = 1,
    ) -> None:
        if not 1 <= weeks <= 52:
            raise ValueError("weeks must be between 1 and 52")
        self.item_service = item_service
        self.run_at = run_at
        self.weeks = weeks
        self._stop_event = threading.Event()

    def run_once(self, *, force: bool = True) -> None:
        forecast = self.item_service.forecast_components(
            weeks=self.weeks,
            force=force,
        )
        logger.info(
            "Component forecast cached for %s week(s): %s item(s)",
            self.weeks,
            len(forecast),
        )

    def seconds_until_next_run(self, now: datetime | None = None) -> float:
        now = now or datetime.now(BERLIN_TIMEZONE)
        if now.tzinfo is None:
            now = now.replace(tzinfo=BERLIN_TIMEZONE)
        else:
            now = now.astimezone(BERLIN_TIMEZONE)

        next_run = datetime.combine(now.date(), self.run_at, BERLIN_TIMEZONE)
        if next_run <= now:
            next_run += timedelta(days=1)
        return (next_run - now).total_seconds()

    def run_forever(self) -> None:
        logger.info(
            "Forecast worker started; daily run at %s Europe/Berlin",
            self.run_at.strftime("%H:%M"),
        )

        # Ensure requests have a cached result immediately after worker startup.
        try:
            self.run_once(force=False)
        except Exception:
            logger.exception("Initial component forecast warm-up failed")

        while not self._stop_event.wait(self.seconds_until_next_run()):
            try:
                self.run_once(force=True)
            except Exception:
                logger.exception("Scheduled component forecast failed")

    def stop(self) -> None:
        self._stop_event.set()


def main() -> None:
    settings = Settings()
    settings.validate()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    service = ItemService(build_item_repository(settings))
    worker = ForecastWorker(
        service,
        run_at=time(settings.forecast_run_hour, settings.forecast_run_minute),
        weeks=settings.forecast_weeks,
    )
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        logger.info("Forecast worker stopping")
        worker.stop()


if __name__ == "__main__":
    main()
