from __future__ import annotations

from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field, model_validator

class GetCurrentTimeArgs(BaseModel):
    pass


def create_current_time_handler(order_service: OrderService):
    def handler(*args: Any, **kwargs: Any) -> dict[str, str]:
        import zoneinfo
        try:
            tz = zoneinfo.ZoneInfo("Europe/Berlin")
        except zoneinfo.ZoneInfoNotFoundError:
            # Fallback configuration for missing OS timezone databases (e.g. Windows)
            from datetime import timezone, timedelta
            tz = timezone(timedelta(hours=2)) 

        now = datetime.now(tz)
        
        return {
            "current_date": now.strftime("%Y-%m-%d"),
            "current_time": now.strftime("%H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "iso_timestamp": now.isoformat()
        }
        
    return handler
