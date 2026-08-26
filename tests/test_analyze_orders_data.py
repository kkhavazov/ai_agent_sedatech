from datetime import date, datetime

import pandas as pd

from services.order_service import OrderService
from tools.factory import build_tool_registry
from tools.orders.analyze_orders import AnalyzeDataArguments, create_analyze_data_handler


class AnalyzeRepository:
    def __init__(self) -> None:
        self.arguments = {}

    def analyze_orders_data(self, **arguments):
        self.arguments = arguments
        return pd.DataFrame.from_records([{
            "CreatedAt": datetime(2026, 8, 21, 12, 30),
            "FinalPrice": 1499.0,
            "Country": "DE",
            "ProductionTime": 3.0,
        }])


def test_analyze_handler_aggregates_dataframe() -> None:
    repository = AnalyzeRepository()
    handler = create_analyze_data_handler(OrderService(repository))
    result = handler(
        metrics=["revenue", "order_count"],
        group_by=["year", "month"], filters={},
        date_from=date(2026, 8, 1), document_type="R",
    )
    assert result["row_count"] == 1
    assert result["rows"][0] == {
        "year": 2026, "month": 8, "revenue": 1499.0, "order_count": 1
    }
    assert repository.arguments["document_type"] == "R"


def test_analyze_tool_is_registered() -> None:
    registry = build_tool_registry(OrderService(AnalyzeRepository()))
    tool_names = [schema["function"]["name"] for schema in registry.schemas()]
    assert "analyze_data" in tool_names
    assert "analyze_orders_data" not in tool_names


def test_analyze_handler_forwards_document_filters() -> None:
    repository = AnalyzeRepository()
    handler = create_analyze_data_handler(OrderService(repository))
    handler(metrics=["order_count"], document_type="L", status=0)
    assert repository.arguments["document_type"] == "L"
    assert repository.arguments["status"] == 0


def test_analyze_handler_defaults_to_final_document_type() -> None:
    repository = AnalyzeRepository()
    handler = create_analyze_data_handler(OrderService(repository))
    handler(metrics=["order_count"])
    assert repository.arguments["document_type"] == "R"


def test_month_grouping_also_includes_year() -> None:
    result = create_analyze_data_handler(OrderService(AnalyzeRepository()))(
        metrics=["order_count"], group_by=["month"]
    )
    assert result["rows"][0]["year"] == 2026
    assert result["rows"][0]["month"] == 8


def test_partial_month_dates_expand_to_month_boundaries() -> None:
    arguments = AnalyzeDataArguments(
        metrics=["order_count"], date_from="2025-06", date_to="2025-06"
    )
    assert arguments.date_from == date(2025, 6, 1)
    assert arguments.date_to == date(2025, 6, 30)


def test_blank_date_to_is_treated_as_open_ended() -> None:
    arguments = AnalyzeDataArguments(metrics=["order_count"], date_to="")
    assert arguments.date_to is None


def test_dates_are_promoted_out_of_filters() -> None:
    arguments = AnalyzeDataArguments(
        metrics=["order_count"],
        filters={"date_from": "2025-06", "country": "DE"},
    )
    assert arguments.date_from == date(2025, 6, 1)
    assert arguments.filters == {"country": "DE"}
