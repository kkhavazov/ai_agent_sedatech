from unittest.mock import patch

import pytest
from pydantic import ValidationError

from analytics.tools import query_website_traffic


def report():
    return {"property": "properties/123", "retrieved_at": "2026-10-02T00:00:00Z",
            "metadata": {"time_zone": "Europe/Berlin"}, "row_count": 2,
            "next_offset": None, "rows": [
                {"dimension_values": [{"value": "20260902"}], "metric_values": [{"value": "20"}]},
                {"dimension_values": [{"value": "20260901"}], "metric_values": [{"value": "10"}]},
            ]}


def test_trend_sorted_with_chart_and_metadata():
    with patch("analytics.ga4_client.GA4Client") as client:
        client.return_value.run_report.return_value = report()
        result = query_website_traffic.invoke({"breakdown": "date", "chart": True})
    assert result["chart"]["data"] == [{"x": "2026-09-01", "y": 10}, {"x": "2026-09-02", "y": 20}]
    assert result["metadata"]["time_zone"] == "Europe/Berlin"


def test_overview_requests_deduplicated_period_total():
    with patch("analytics.ga4_client.GA4Client") as client:
        data = report()
        data["rows"] = [{"metric_values": [{"value": "123"}]}]
        client.return_value.run_report.return_value = data
        result = query_website_traffic.invoke({"metric": "activeUsers"})
        assert client.return_value.run_report.call_args.kwargs["dimensions"] == []
    assert result["rows"] == [{"activeUsers": 123}]


def test_partial_report_is_disclosed():
    with patch("analytics.ga4_client.GA4Client") as client:
        data = report()
        data["next_offset"] = 2
        client.return_value.run_report.return_value = data
        result = query_website_traffic.invoke({"breakdown": "date", "chart": True})
    assert result["truncated"] and result["warnings"]
    assert "partial" in result["chart"]["title"]


def test_missing_configuration_does_not_crash_chat():
    with patch("analytics.ga4_client.GA4Client", side_effect=ValueError("Missing property")):
        result = query_website_traffic.invoke({})
    assert result["error"]["type"] == "ValueError"
    assert "rows" not in result


@pytest.mark.parametrize("args", [{"limit": 1000}, {"metric": "madeUp"}, {"breakdown": "sql"}])
def test_tool_rejects_invalid_arguments(args):
    with pytest.raises(ValidationError):
        query_website_traffic.invoke(args)
