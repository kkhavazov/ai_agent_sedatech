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
        "Platform": "Amazon", "FinalPrice": Decimal("100.25"),
        "FirstPrice": Decimal("119.30"), "Taxes": Decimal("19.05"),
        "Country": "DE", "Postcode": "12345", "City": "Berlin",
    }]
    connection = Mock()
    connection.cursor.return_value = cursor
    repository = SqlServerOrderRepository("server", "user", "password", "database")
    repository._connect = Mock(return_value=connection)
    return repository, cursor, connection


def test_foreign_currency_prices_and_query_filters_are_preserved():
    repository, cursor, connection = make_repository()
    frame = repository.analyze_orders_data(
        document_type="R", status=0,
        date_from=date(2026, 11, 1), date_to=date(2026, 11, 18),
    )
    query, parameters = cursor.execute.call_args.args
    assert "t1.FremdwaehrungNetto AS FinalPrice" in query
    assert "t1.FremdwaehrungBrutto AS FirstPrice" in query
    assert parameters == ("R", 0, date(2026, 11, 1), date(2026, 11, 18))
    assert "t1.AngelegtAm < DATEADD(day, 1, %s)" in query
    assert frame.iloc[0]["FinalPrice"] == Decimal("100.25")
    assert frame.iloc[0]["FirstPrice"] == Decimal("119.30")
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_foreign_currency_net_price_reaches_revenue_aggregation():
    repository, _, _ = make_repository()
    result = create_analyze_data_handler(OrderService(repository))(
        metrics=["revenue", "order_count"], group_by=["platform"],
    )
    assert result["rows"] == [{
        "platform": "Amazon", "revenue": Decimal("100.25"), "order_count": 1,
    }]


def test_default_analysis_metrics_work_with_repository_columns():
    repository, _, _ = make_repository()
    result = create_analyze_data_handler(OrderService(repository))(
        **AnalyzeDataArguments(group_by=[]).model_dump()
    )
    assert result["rows"] == [{"revenue": Decimal("100.25"), "order_count": 1}]


@pytest.mark.parametrize("max_rows, expected_limit", [(0, 1), (25, 25), (20000, 10000)])
def test_query_row_limit_is_bounded(max_rows, expected_limit):
    repository, cursor, _ = make_repository()
    repository.analyze_orders_data(max_rows=max_rows)
    assert f"SELECT TOP ({expected_limit})" in cursor.execute.call_args.args[0]
