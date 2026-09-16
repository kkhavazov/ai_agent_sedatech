from datetime import date
from unittest.mock import MagicMock

import pymssql
import pytest

from repositories.sqlserver_emails_repository import SqlServerEmailsRepository
from services.order_service import OrderService
from repositories.demo_order_repository import DemoOrderRepository
from tools.factory import build_tool_registry


def make_repository():
    repository = SqlServerEmailsRepository("server", "user", "password", "database")
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = [{"Email": "customer@example.com"}]
    repository._connect = MagicMock(return_value=connection)
    return repository, connection, cursor


@pytest.mark.parametrize(
    "filters,parameters",
    [
        ({}, ()),
        ({"date_from": "2026-09-01"}, (date(2026, 9, 1),)),
        ({"date_to": "2026-09-16"}, (date(2026, 9, 16),)),
        (
            {"date_from": "2026-09-01", "date_to": "2026-09-16"},
            (date(2026, 9, 1), date(2026, 9, 16)),
        ),
    ],
)
def test_optional_dates_are_bound_parameters(filters, parameters):
    repository, connection, cursor = make_repository()
    assert repository.get_emails(**filters) == ["customer@example.com"]
    query, bound = cursor.execute.call_args.args
    assert bound == parameters
    assert "Vertreter = 8" in query
    assert "Belegtyp = 'R'" in query
    assert ("Datum >= %s" in query) == ("date_from" in filters)
    assert ("Datum < DATEADD(day, 1, %s)" in query) == ("date_to" in filters)
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("filters", [
    {"platform": "amazon"},
    {"date_from": "2026-09-16", "date_to": "2026-09-01"},
    {"date_from": "2026-09-01'; DROP TABLE BELEG;--"},
])
def test_invalid_filters_do_not_connect(filters):
    repository, _, _ = make_repository()
    with pytest.raises(ValueError):
        repository.get_emails(**filters)
    repository._connect.assert_not_called()


def test_database_error_closes_resources():
    repository, connection, cursor = make_repository()
    cursor.execute.side_effect = pymssql.Error("unavailable")
    with pytest.raises(RuntimeError, match="DATABASE_QUERY_ERROR"):
        repository.get_emails()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_registered_email_tool_defaults_validates_and_returns_empty_results():
    repository, _, cursor = make_repository()
    registry = build_tool_registry(
        OrderService(DemoOrderRepository()), emails_repository=repository
    )
    result = registry.execute("get_emails", {})
    assert result["success"] is True
    assert result["data"] == {
        "platform": "sedatech", "emails": ["customer@example.com"], "count": 1
    }
    for arguments in (
        {"platform": "amazon"},
        {"date_from": "invalid"},
        {"date_from": "2026-09-16", "date_to": "2026-09-01"},
    ):
        result = registry.execute("get_emails", arguments)
        assert result["error"]["code"] == "INVALID_ARGUMENTS"
    cursor.fetchall.return_value = []
    assert registry.execute("get_emails", {})["data"]["emails"] == []


def test_email_tool_is_not_registered_without_repository():
    registry = build_tool_registry(OrderService(DemoOrderRepository()))
    assert "get_emails" not in {
        schema["function"]["name"] for schema in registry.schemas()
    }
