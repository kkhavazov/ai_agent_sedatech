"""Bounded GA4 tools for the internal assistant."""

from datetime import datetime
from typing import Literal

from langchain.tools import tool
from pydantic import BaseModel, Field


class WebsiteTrafficArgs(BaseModel):
    start_date: str = Field(default="28daysAgo", description="Inclusive range START. Last 30 days: 30daysAgo.")
    end_date: str = Field(default="yesterday", description="Inclusive range END. Last 30 days: yesterday, NOT 30daysAgo. YYYY-MM-DD also accepted.")
    breakdown: Literal["overview", "date", "channel", "source", "landing_page", "device", "country"] = "overview"
    metric: Literal["activeUsers", "sessions", "screenPageViews", "engagementRate", "ecommercePurchases", "purchaseRevenue"] = "sessions"
    chart: bool = False
    limit: int = Field(default=100, ge=1, le=366)


@tool(args_schema=WebsiteTrafficArgs)
def query_website_traffic(
    start_date: str = "28daysAgo",
    end_date: str = "yesterday",
    breakdown: str = "overview",
    metric: str = "sessions",
    chart: bool = False,
    limit: int = 100,
) -> dict:
    """Read GA4 website traffic, acquisition channels, landing pages, devices,
    countries, engagement, and tracked purchases/revenue. Use overview for true
    period totals (never sum daily active users). Use date for trends and charts;
    set limit=366 for long daily reports. For period comparisons, call once per
    period with the same metric and breakdown. Ecommerce requires site tracking.
    This reports website analytics, not SQL order revenue or inventory.
    For 'last 30 days', use start_date='30daysAgo', end_date='yesterday'.
    Do not use 30daysAgo as the end of a last-30-days report.
    """
    # Lazy import/construction keeps missing GA4 configuration from breaking chat.
    from analytics.ga4_client import GA4Client

    dimension = {
        "overview": None, "date": "date", "channel": "sessionDefaultChannelGroup",
        "source": "sessionSourceMedium", "landing_page": "landingPage",
        "device": "deviceCategory", "country": "country",
    }[breakdown]
    try:
        report = GA4Client().run_report(
            start_date=start_date, end_date=end_date,
            dimensions=[dimension] if dimension else [], metrics=[metric], limit=limit,
        )
    except Exception as exc:
        return {"error": {"type": type(exc).__name__, "message": str(exc)},
                "answer": "Website analytics is unavailable; this is not zero traffic."}

    rows = []
    for row in report.get("rows", []):
        value = row["metric_values"][0]["value"]
        record = {metric: float(value) if "." in value or "e" in value.lower() else int(value)}
        if dimension:
            label = row["dimension_values"][0]["value"]
            if dimension == "date":
                label = datetime.strptime(label, "%Y%m%d").date().isoformat()
            record[breakdown] = label
        rows.append(record)
    if breakdown == "date":
        rows.sort(key=lambda row: row["date"])
    truncated = report.get("next_offset") is not None
    warnings = []
    if truncated:
        warnings.append("Only part of the report is returned. Narrow the dates or increase limit; do not treat these rows as the complete report.")
    if not rows:
        warnings.append("GA4 returned no rows; this does not establish that tracking is configured correctly.")
    result = {
        "source": "GA4", "property": report["property"],
        "start_date": start_date, "end_date": end_date,
        "retrieved_at": report["retrieved_at"], "metadata": report.get("metadata", {}),
        "metric": metric, "breakdown": breakdown, "rows": rows,
        "row_count": report.get("row_count", len(rows)), "truncated": truncated,
        "warnings": warnings,
    }
    if chart and rows and dimension:
        result["chart"] = {
            "type": "line" if breakdown == "date" else "bar",
            "title": f"Website {metric}: {start_date} to {end_date}" + (" (partial report)" if truncated else ""),
            "x_label": breakdown, "y_label": metric,
            "x_type": "temporal" if breakdown == "date" else "categorical",
            "data": [{"x": row[breakdown], "y": row[metric]} for row in rows],
        }
    return result
