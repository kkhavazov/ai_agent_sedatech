"""Read-only GA4 reporting client, independent of the agent and SQL Server."""

from __future__ import annotations

import math
import os
import re
from datetime import date, datetime, timezone
from typing import Sequence

import google.auth
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest, RunReportResponse,
)


READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


def _validate_date(value: str) -> None:
    if value in {"today", "yesterday"} or re.fullmatch(r"[0-9]+daysAgo", value):
        return
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Dates must be YYYY-MM-DD, today, yesterday, or NdaysAgo")
    date.fromisoformat(value)


class GA4Client:
    """One configured property; credentials are loaded only on the first report.

    Uses Application Default Credentials (including GOOGLE_APPLICATION_CREDENTIALS).
    An SDK client may be injected for testing. No network calls occur on import.
    """

    def __init__(
        self,
        property_id: str | None = None,
        *,
        timeout_seconds: float = 30,
        client: BetaAnalyticsDataClient | None = None,
    ) -> None:
        property_id = (property_id if property_id is not None else os.getenv("GA4_PROPERTY_ID", "")).strip()
        property_id = property_id.removeprefix("properties/")
        if not re.fullmatch(r"[0-9]+", property_id):
            raise ValueError("GA4_PROPERTY_ID must be a numeric property ID, not a G- measurement ID")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.property = f"properties/{property_id}"
        self.timeout_seconds = timeout_seconds
        self._client = client

    def run_report(
        self,
        *,
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        metrics: Sequence[str] = ("activeUsers", "sessions", "screenPageViews"),
        dimensions: Sequence[str] = (),
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """Return one bounded page plus GA4 metadata and explicit pagination.

        Metric values remain Google's decimal strings, avoiding precision loss.
        Dates are inclusive and relative dates use the GA4 property's timezone.
        Google SDK exceptions propagate so callers can distinguish permission,
        invalid-report, quota, and transport failures from an empty report.
        """
        _validate_date(start_date)
        _validate_date(end_date)
        if re.fullmatch(r"[0-9-]{10}", start_date) and re.fullmatch(r"[0-9-]{10}", end_date):
            if date.fromisoformat(start_date) > date.fromisoformat(end_date):
                raise ValueError("start_date must not be after end_date")
        for names, maximum, label in ((metrics, 10, "metrics"), (dimensions, 9, "dimensions")):
            if isinstance(names, str) or len(names) > maximum:
                raise ValueError(f"{label} must be a sequence of at most {maximum} names")
            if any(not isinstance(name, str) or not name.strip() for name in names):
                raise ValueError(f"{label} must contain nonempty names")
            if len(set(names)) != len(names):
                raise ValueError(f"{label} must not contain duplicates")
        if not metrics:
            raise ValueError("At least one metric is required")
        if type(limit) is not int or not 1 <= limit <= 250_000:
            raise ValueError("limit must be an integer between 1 and 250000")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer")

        request = RunReportRequest(
            property=self.property,
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimensions=[Dimension(name=name) for name in dimensions],
            metrics=[Metric(name=name) for name in metrics],
            limit=limit,
            offset=offset,
            return_property_quota=True,
        )
        if self._client is None:
            credentials, _ = google.auth.default(scopes=[READONLY_SCOPE])
            self._client = BetaAnalyticsDataClient(credentials=credentials)
        # Keep latency bounded; the service/worker can implement its retry policy.
        response = self._client.run_report(request=request, timeout=self.timeout_seconds, retry=None)
        report = RunReportResponse.to_dict(response)
        returned = len(response.rows)
        report.update({
            "property": self.property,
            "start_date": start_date,
            "end_date": end_date,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "offset": offset,
            "limit": limit,
            "next_offset": offset + returned if returned and offset + returned < response.row_count else None,
        })
        return report
