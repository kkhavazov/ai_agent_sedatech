from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from repositories.sqlserver_order_repository import SqlServerOrderRepository
from services.order_service import OrderService
from tools.orders.analyze_orders import AnalyzeDataArguments, create_analyze_data_handler


def make_repository():
    cursor = Mock()
    cursor.fetchall.return_value = [{
        "CreatedAt": datetime(2026, 11, 17, 10),
        "CustomerNumber": "K123456", "DocumentType": "R", "Status": 0,
        "Platform": "Amazon", "selling_price": Decimal("119.30"),
        "production_cost": Decimal("80.00"), "gross_profit": Decimal("20.25"),
        "Taxes": Decimal("19.05"),
        "Country": "DE", "Postcode": "12345", "City": "Berlin",
    }]
    connection = Mock()
    connection.cursor.return_value = cursor
    repository = SqlServerOrderRepository("server", "user", "password", "database")
    repository._connect = Mock(return_value=connection)
    return repository, cursor, connection


def test_recorded_order_prices_and_query_filters_are_preserved():
    repository, cursor, connection = make_repository()
    frame = repository.analyze_orders_data(
        document_type="R", status=0,
        date_from=date(2026, 11, 1), date_to=date(2026, 11, 18),
    )
    query, parameters = cursor.execute.call_args.args
    assert "t1.EuroBrutto AS selling_price" in query
    assert "t1.UebernahmeOffen AS production_cost" in query
    assert "t1.ErloesEuro AS gross_profit" in query
    assert "Fremdwaehrung" not in query
    assert parameters == ("R", 0, date(2026, 11, 1), date(2026, 11, 18))
    assert "t1.AngelegtAm < DATEADD(day, 1, %s)" in query
    assert frame.iloc[0]["selling_price"] == Decimal("119.30")
    assert frame.iloc[0]["production_cost"] == Decimal("80.00")
    assert frame.iloc[0]["gross_profit"] == Decimal("20.25")
    assert "FinalPrice" not in frame.columns
    assert "FirstPrice" not in frame.columns
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_gross_selling_price_reaches_revenue_aggregation():
    repository, _, _ = make_repository()
    result = create_analyze_data_handler(OrderService(repository))(
        metrics=["revenue", "order_count"], group_by=["platform"],
    )
    assert result["rows"] == [{
        "platform": "Amazon", "revenue": Decimal("119.30"), "order_count": 1,
    }]


def test_default_analysis_metrics_work_with_repository_columns():
    repository, _, _ = make_repository()
    result = create_analyze_data_handler(OrderService(repository))(
        **AnalyzeDataArguments(group_by=[]).model_dump()
    )
    assert result["rows"] == [{"revenue": Decimal("119.30"), "order_count": 1}]


@pytest.mark.parametrize("group_by", [[], ["platform"]])
def test_price_metrics_sum_recorded_values_through_tool_schema(group_by):
    repository, cursor, _ = make_repository()
    cursor.fetchall.return_value *= 2
    arguments = AnalyzeDataArguments(
        metrics=["selling_price", "production_cost", "gross_profit"],
        group_by=group_by, sort_by="gross_profit", sort_direction="desc",
    )
    result = create_analyze_data_handler(OrderService(repository))(**arguments.model_dump())
    expected = {
        "selling_price": Decimal("238.60"),
        "production_cost": Decimal("160.00"),
        "gross_profit": Decimal("40.50"),
    }
    if group_by:
        expected["platform"] = "Amazon"
    assert result["rows"] == [expected]


@pytest.mark.parametrize("group_by", [[], ["platform"]])
@pytest.mark.parametrize("value", [None, Decimal("0"), Decimal("-10.50")])
def test_price_metrics_preserve_unknown_zero_and_negative_values(group_by, value):
    repository, cursor, _ = make_repository()
    metrics = ["selling_price", "production_cost", "gross_profit"]
    cursor.fetchall.return_value[0].update({metric: value for metric in metrics})
    result = create_analyze_data_handler(OrderService(repository))(
        metrics=metrics, group_by=group_by,
    )
    for metric in metrics:
        assert result["rows"][0][metric] == value


def test_empty_analysis_retains_price_columns():
    repository, cursor, _ = make_repository()
    cursor.fetchall.return_value = []
    result = create_analyze_data_handler(OrderService(repository))(
        metrics=["revenue", "production_cost", "gross_profit", "order_count"],
    )
    assert result["rows"] == [{
        "revenue": None, "production_cost": None, "gross_profit": None, "order_count": 0,
    }]


@pytest.mark.parametrize("max_rows, expected_limit", [(0, 1), (25, 25), (20000, 10000)])
def test_query_row_limit_is_bounded(max_rows, expected_limit):
    repository, cursor, _ = make_repository()
    repository.analyze_orders_data(max_rows=max_rows)
    assert f"SELECT TOP ({expected_limit})" in cursor.execute.call_args.args[0]
