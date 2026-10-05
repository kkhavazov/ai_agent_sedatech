from unittest.mock import Mock, patch

import pytest
from google.api_core.exceptions import PermissionDenied
from google.analytics.data_v1beta.types import RunReportResponse

from analytics.ga4_client import GA4Client, READONLY_SCOPE


def test_report_preserves_precision_metadata_and_pagination():
    sdk = Mock()
    sdk.run_report.return_value = RunReportResponse(
        dimension_headers=[{"name": "country"}],
        metric_headers=[{"name": "purchaseRevenue", "type_": "TYPE_FLOAT"}],
        rows=[{"dimension_values": [{"value": "Germany"}],
               "metric_values": [{"value": "1234567890.123456"}]}],
        row_count=3,
        metadata={"time_zone": "Europe/Berlin", "subject_to_thresholding": True},
    )
    client = GA4Client("123", client=sdk)
    result = client.run_report(dimensions=["country"], metrics=["purchaseRevenue"], limit=1)
    request = sdk.run_report.call_args.kwargs["request"]
    assert request.property == "properties/123"
    assert request.return_property_quota
    assert request.date_ranges[0].end_date == "yesterday"
    assert sdk.run_report.call_args.kwargs["retry"] is None
    assert sdk.run_report.call_args.kwargs["timeout"] == 30
    assert result["rows"][0]["metric_values"][0]["value"] == "1234567890.123456"
    assert result["metadata"]["subject_to_thresholding"] is True
    assert result["metadata"]["time_zone"] == "Europe/Berlin"
    assert result["next_offset"] == 1
    assert result["retrieved_at"]


@pytest.mark.parametrize("arguments", [
    {"start_date": "2026-02-30"},
    {"start_date": "last month"},
    {"start_date": "2026-02-02", "end_date": "2026-02-01"},
    {"metrics": []}, {"metrics": "sessions"},
    {"metrics": ["sessions", "sessions"]}, {"dimensions": [""]},
    {"limit": 0}, {"limit": 250001}, {"limit": True}, {"offset": -1},
])
def test_invalid_report_never_calls_google(arguments):
    sdk = Mock()
    with pytest.raises(ValueError):
        GA4Client("123", client=sdk).run_report(**arguments)
    sdk.run_report.assert_not_called()


def test_environment_and_lazy_readonly_credentials(monkeypatch):
    monkeypatch.setenv("GA4_PROPERTY_ID", "123")
    with patch("analytics.ga4_client.google.auth.default") as auth, patch(
        "analytics.ga4_client.BetaAnalyticsDataClient"
    ) as sdk:
        auth.return_value = (Mock(), "cloud-project")
        sdk.return_value.run_report.return_value = RunReportResponse()
        client = GA4Client()
        auth.assert_not_called()
        assert client.run_report()["next_offset"] is None
        auth.assert_called_once_with(scopes=[READONLY_SCOPE])
        client.run_report()
        assert auth.call_count == 1


def test_permission_failure_is_not_an_empty_report():
    sdk = Mock()
    sdk.run_report.side_effect = PermissionDenied("Access denied")
    with pytest.raises(PermissionDenied):
        GA4Client("properties/123", client=sdk).run_report()
    assert sdk.run_report.call_count == 1


@pytest.mark.parametrize("property_id", ["", "G-ABC123", "123/other"])
def test_rejects_invalid_property(property_id):
    with pytest.raises(ValueError, match="property ID"):
        GA4Client(property_id)
