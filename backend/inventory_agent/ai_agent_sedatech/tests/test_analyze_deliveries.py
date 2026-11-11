import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from repositories.delivery_repository import DELIVERY_COLUMNS
from repositories import sqlserver_delivery_repository as sql_module
from repositories.sqlserver_delivery_repository import SqlServerDeliveryRepository
from services.delivery_service import DeliveryService
from services.order_service import OrderService
from tools.factory import build_tool_registry


class DeliveryRepositoryStub:
    def __init__(self, rows):
        self.frame = pd.DataFrame(rows, columns=DELIVERY_COLUMNS)
        self.arguments = None

    def analyze_deliveries_data(self, **arguments):
        self.arguments = arguments
        return self.frame


def delivery_row(**overrides):
    return {
        "delivery_number": "SUP-123", "component_sku": "RAM-16",
        "component_name": "16GB RAM", "provider": "Supplier A",
        "delivery_date": datetime(2026, 11, 9, 14, 30),
        "status": "received", "quantity": Decimal("3.5"), **overrides,
    }


def registry_for(repository):
    # Sales access must never be used to fulfill a supplier delivery request.
    sales = MagicMock()
    sales.analyze_orders_data.side_effect = AssertionError("Queried sales for a delivery")
    return build_tool_registry(
        OrderService(sales), delivery_service=DeliveryService(repository),
    )


@pytest.mark.parametrize("status", ["received", "waiting", None])
def test_delivery_tool_forwards_filters_and_returns_json_table(status):
    repository = DeliveryRepositoryStub([delivery_row(status=status or "received")])
    result = registry_for(repository).execute("analyze_deliveries", {
        "components": ["RAM-16", "SSD-1TB"], "provider": "Supplier A",
        "date_from": "2026-11-01", "date_to": "2026-11-30",
        "status": status, "limit": 20,
    })
    assert result["success"] is True
    assert repository.arguments == {
        "components": ["RAM-16", "SSD-1TB"], "provider": "Supplier A",
        "date_from": date(2026, 11, 1), "date_to": date(2026, 11, 30),
        "status": status, "max_rows": 21,
    }
    table = result["data"]
    assert table["order_type"] == "incoming_delivery"
    assert table["columns"] == DELIVERY_COLUMNS
    assert table["row_count"] == 1
    assert table["truncated"] is False
    assert table["rows"][0]["quantity"] == 3.5
    assert table["rows"][0]["delivery_date"].startswith("2026-11-09")
    json.dumps(table, allow_nan=False)


@pytest.mark.parametrize("arguments", [
    {"status": 0}, {"status": "sent"}, {"components": [" "]},
    {"provider": " "}, {"document_type": "R"},
    {"date_from": "2026-11-30", "date_to": "2026-11-01"},
    {"limit": 0}, {"limit": 10001},
])
def test_invalid_delivery_filters_fail_before_repository_access(arguments):
    repository = DeliveryRepositoryStub([])
    result = registry_for(repository).execute("analyze_deliveries", arguments)
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert repository.arguments is None


def test_empty_delivery_table_preserves_columns_and_unfiltered_defaults():
    repository = DeliveryRepositoryStub([])
    result = registry_for(repository).execute("analyze_deliveries", {})
    assert result["success"] is True
    assert result["data"]["rows"] == []
    assert result["data"]["row_count"] == 0
    assert result["data"]["columns"] == DELIVERY_COLUMNS
    assert result["data"]["truncated"] is False
    assert repository.arguments == dict(
        components=[], date_from=None, date_to=None, provider=None,
        status=None, max_rows=1001,
    )


def test_truncation_and_missing_date_are_explicit():
    repository = DeliveryRepositoryStub([
        delivery_row(delivery_date=pd.NaT, status="waiting"), delivery_row(),
    ])
    result = registry_for(repository).execute("analyze_deliveries", {"limit": 1})
    assert result["success"] is True
    assert result["data"]["row_count"] == 1
    assert result["data"]["truncated"] is True
    assert result["data"]["rows"][0]["delivery_date"] is None
    json.dumps(result["data"], allow_nan=False)


@pytest.mark.parametrize("bad_data", [
    pd.DataFrame({"CreatedAt": [], "FinalPrice": []}),
    pd.DataFrame([delivery_row(status=0)]),
])
def test_sales_shaped_data_is_rejected(bad_data):
    repository = DeliveryRepositoryStub([])
    repository.frame = bad_data
    result = registry_for(repository).execute("analyze_deliveries", {})
    assert result["success"] is False
    assert result["data"] is None


def test_unconfigured_delivery_repository_reports_error_not_no_matches():
    result = registry_for(None).execute("analyze_deliveries", {})
    assert result["success"] is False
    assert "No incoming-delivery repository" in result["error"]["message"]


def sql_repository():
    return SqlServerDeliveryRepository(
        server="example", user="example", password="example", database="example",
    )


def test_sql_placeholder_does_not_connect_or_return_empty_table(monkeypatch):
    repository = sql_repository()
    monkeypatch.setattr(sql_module, "ANALYZE_DELIVERIES_QUERY", "")
    connect = MagicMock(side_effect=AssertionError("Connected before SQL was configured"))
    monkeypatch.setattr(repository, "_connect", connect)
    result = registry_for(repository).execute("analyze_deliveries", {})
    assert result["success"] is False
    assert "ANALYZE_DELIVERIES_QUERY" in result["error"]["message"]
    connect.assert_not_called()


@pytest.mark.parametrize("rows", [[], [delivery_row()]])
def test_sql_execution_binds_filters_and_closes_connection(monkeypatch, rows):
    repository = sql_repository()
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchmany.return_value = rows
    monkeypatch.setattr(repository, "_connect", lambda: connection)
    provider = "O'Reilly supplier"
    result = registry_for(repository).execute("analyze_deliveries", {
        "provider": provider, "components": ["RAM-16"], "limit": 10,
    })
    assert result["success"] is True
    query, parameters = cursor.execute.call_args.args
    assert "ART.Artikelnummer LIKE %s" in query
    assert "B.Name = %s" in query
    assert provider not in query
    assert parameters == (11, "%RAM-16%", provider)
    cursor.fetchmany.assert_called_once_with(11)
    connection.__exit__.assert_called_once()


def test_component_attribute_filters_are_normalized_before_repository_access():
    repository = DeliveryRepositoryStub([])
    result = registry_for(repository).execute("analyze_deliveries", {
        "components": [{"ram_capacity": 16, "ram_ddr": 5}, {
            "cpu_manufacturer": "Intel", "cpu_model": "14900kf",
        }],
    })
    assert result["success"] is True
    ram, cpu = repository.arguments["components"]
    assert ram["category"] == "ME"
    assert cpu["category"] == "CP"
    assert cpu["cpu_model"] == "14900KF"


@pytest.mark.parametrize("component", [
    {}, {"category": "CP", "ram_capacity": 16}, {"cpu_model": "14900KF"},
    {"sku": "CP", "unknown_filter": True},
])
def test_invalid_component_attribute_filters_do_not_query(component):
    repository = DeliveryRepositoryStub([])
    result = registry_for(repository).execute("analyze_deliveries", {"components": [component]})
    assert result["success"] is False
    assert repository.arguments is None


@pytest.fixture
def delivery_sql(monkeypatch):
    """Execute generated SQL locally, adapting only SQL Server limit/date syntax."""
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.executescript("""
        CREATE TABLE BELEG (Belegnummer TEXT, Belegtyp TEXT, Name TEXT, UebernahmeOffen REAL);
        CREATE TABLE BELEGP (
            Belegnummer TEXT, Belegtyp TEXT, Zeilentyp TEXT, Artikelnummer TEXT,
            Bezeichnung TEXT, EditMenge REAL, Datum TEXT
        );
        CREATE TABLE ART (Artikelnummer TEXT, ArtikelGruppe TEXT, Bezeichnung TEXT);
    """)
    database.executemany("INSERT INTO ART VALUES (?, ?, ?)", [
        ("ME-16", "ME", "16GB DDR5 6000"),
        ("CP-KF", "CP", "Intel Core i9-14900KF"),
        ("CP-K", "CP", "Intel Core i9-14900K"),
    ])
    database.executemany("INSERT INTO BELEG VALUES (?, ?, ?, ?)", [
        ("P1", "B", "Supplier A", -2),
        ("P1", "R", "Sales customer", 0),  # Same number must not duplicate supplier rows.
        ("P2", "B", "Supplier A", 0),
        ("P3", "B", "Supplier B", 2),
        ("P4", "B", "Supplier A", None),
        ("P5", "R", "Sales customer", 0),
    ])
    database.executemany("INSERT INTO BELEGP VALUES (?, ?, ?, ?, ?, ?, ?)", [
        ("P1", "B", "A", "ME-16", "16GB DDR5 6000", 10, "2026-11-01 00:00:00"),
        ("P1", "B", "A", "CP-KF", "Intel Core i9-14900KF", 5, "2026-11-01 00:00:00"),
        ("P2", "B", "A", "CP-K", "Intel Core i9-14900K", 4, "2026-11-09 23:59:59"),
        ("P3", "B", "A", "ME-16", "16GB DDR5 6000", 7, "2026-11-10 00:00:00"),
        ("P4", "B", "A", "ME-16", "Unknown status", 99, "2026-11-09 12:00:00"),
        ("P5", "R", "A", "ME-16", "Customer sale", 99, "2026-11-09 12:00:00"),
        ("P1", "B", "T", "ME-16", "Text line", 99, "2026-11-09 12:00:00"),
    ])
    repository = sql_repository()
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value

    def execute(query, parameters):
        query = query.replace("SELECT TOP (%s)", "SELECT")
        query = query.replace("DATEADD(day, 1, %s)", "datetime(%s, '+1 day')")
        query = query.replace("%s", "?") + " LIMIT ?"
        sql_cursor = database.execute(query, (*parameters[1:], parameters[0]))
        cursor.fetchmany.side_effect = lambda count: [dict(row) for row in sql_cursor.fetchmany(count)]

    cursor.execute.side_effect = execute
    monkeypatch.setattr(repository, "_connect", lambda: connection)
    try:
        yield registry_for(repository)
    finally:
        database.close()


@pytest.mark.parametrize("arguments, expected", [
    ({}, [("P3", "ME-16", "received"), ("P2", "CP-K", "received"),
          ("P1", "CP-KF", "waiting"), ("P1", "ME-16", "waiting")]),
    ({"status": "waiting"}, [("P1", "CP-KF", "waiting"), ("P1", "ME-16", "waiting")]),
    ({"status": "received"}, [("P3", "ME-16", "received"), ("P2", "CP-K", "received")]),
    ({"date_from": "2026-11-01", "date_to": "2026-11-09", "status": "received",
      "provider": "Supplier A"}, [("P2", "CP-K", "received")]),
    ({"date_from": "2026-11-01", "date_to": "2026-11-01"},
     [("P1", "CP-KF", "waiting"), ("P1", "ME-16", "waiting")]),
    ({"components": ["CP-"]}, [("P2", "CP-K", "received"), ("P1", "CP-KF", "waiting")]),
    ({"components": [{"cpu_manufacturer": "Intel", "cpu_model": "14900K"}]},
     [("P2", "CP-K", "received")]),
    ({"components": [{"ram_capacity": 16, "ram_ddr": 5}, "CP-"],
      "provider": "Supplier A", "status": "waiting"},
     [("P1", "CP-KF", "waiting"), ("P1", "ME-16", "waiting")]),
    ({"components": [{"ram_capacity": 32}]}, []),
    ({"components": ["x' OR 1=1 --"]}, []),
])
def test_delivery_sql_filters_real_rows(delivery_sql, arguments, expected):
    result = delivery_sql.execute("analyze_deliveries", arguments)
    assert result["success"] is True, result["error"]
    assert [(row["delivery_number"], row["component_sku"], row["status"])
            for row in result["data"]["rows"]] == expected
    assert result["data"]["date_basis"] == "supplier_document_date"


def test_delivery_sql_applies_limit_after_filtering(delivery_sql):
    result = delivery_sql.execute("analyze_deliveries", {"status": "waiting", "limit": 1})
    assert result["success"] is True
    assert result["data"]["row_count"] == 1
    assert result["data"]["truncated"] is True
    assert result["data"]["rows"][0]["quantity"] == 5
