from datetime import date
from unittest.mock import MagicMock

import pymssql
import pytest
import requests

from repositories.sqlserver_emails_repository import SqlServerEmailsRepository
from services.order_service import OrderService
from repositories.demo_order_repository import DemoOrderRepository
from tools.factory import build_tool_registry


@pytest.fixture(autouse=True)
def ticket_session(monkeypatch):
    session = MagicMock()
    session.get.return_value.json.return_value = {"data": []}
    session.__enter__.return_value = session
    monkeypatch.setattr("repositories.sqlserver_emails_repository.requests.Session", lambda: session)
    return session


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
    assert repository.get_emails(**filters) == [{"email": "customer@example.com", "customer_service": False}]
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
        "platform": "sedatech", "emails": [{"email": "customer@example.com", "customer_service": False}], "count": 1
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


def test_checks_every_email_and_marks_nonempty_results(ticket_session):
    repository, connection, cursor = make_repository()
    repository.tickets_api_url = "http://backend:8000/tickets"
    cursor.fetchall.return_value = [{"Email": "one+tag@example.com"}, {"Email": "two@example.com"}]
    ticket_session.get.return_value.json.side_effect = [{"data": [{"id": 1}]}, {"data": []}]
    assert repository.get_emails() == [
        {"email": "one+tag@example.com", "customer_service": True},
        {"email": "two@example.com", "customer_service": False},
    ]
    assert [call.args[0] for call in ticket_session.get.call_args_list] == [
        "http://backend:8000/tickets/emails/one%2Btag%40example.com",
        "http://backend:8000/tickets/emails/two%40example.com",
    ]
    connection.close.assert_called_once()


@pytest.mark.parametrize("payload", [{}, {"data": None}, {"data": {}}, []])
def test_invalid_ticket_response_is_not_marked_false(ticket_session, payload):
    repository, _, _ = make_repository()
    ticket_session.get.return_value.json.return_value = payload
    with pytest.raises(RuntimeError, match="TICKET_LOOKUP_ERROR"):
        repository.get_emails()


def test_ticket_request_failure_is_not_marked_false(ticket_session):
    repository, _, _ = make_repository()
    ticket_session.get.side_effect = requests.Timeout()
    with pytest.raises(RuntimeError, match="TICKET_LOOKUP_ERROR"):
        repository.get_emails()


def test_no_ticket_requests_for_empty_emails(ticket_session):
    repository, _, cursor = make_repository()
    cursor.fetchall.return_value = []
    assert repository.get_emails() == []
    ticket_session.get.assert_not_called()


@pytest.mark.parametrize("status", [404, 401, 502])
def test_ticket_http_failure_reports_status(ticket_session, status):
    repository, _, _ = make_repository()
    response = requests.Response()
    response.status_code = status
    ticket_session.get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as error:
        repository.get_emails()
    if status == 404:
        assert "rebuild the backend" in str(error.value)
