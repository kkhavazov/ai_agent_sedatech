from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from repositories.sqlserver_order_repository import SqlServerOrderRepository
from services.order_service import OrderService
from tools.order_tools import build_get_order_tool
from tools.registry import ToolRegistry


TEXT_FIELDS = (
    "tax_number", "tracking_number", "company_name", "email",
    "phone_number", "language",
)


def lookup(row):
    cursor = Mock()
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = [
        {"Artikelnummer": "PC001", "Bezeichnung": "PC", "Menge": 1,
         "KalkpreisEuro": 100, "Zeilentyp": "H"},
        {"Artikelnummer": "CP001", "Bezeichnung": "CPU", "Menge": 1,
         "KalkpreisEuro": 50, "Zeilentyp": "K"},
    ]
    connection = Mock()
    connection.cursor.return_value = cursor
    repository = SqlServerOrderRepository("server", "user", "password", "database")
    repository._connect = Mock(return_value=connection)
    registry = ToolRegistry()
    registry.register(build_get_order_tool(OrderService(repository)))
    return registry.execute("get_order", {"order_number": " ra171165 "}), cursor


def order_row():
    return {
        "Belegnummer": "RA171165", "Belegtyp": "R", "Status": 0,
        "date_created": datetime(2026, 11, 17, 14, 30),
        "Vorname": "Ada", "Name": "Example", "country": "DE",
        "price": Decimal("1507.02"),
        "tracking_number": "001234567890", "tax_number": "DE001234567",
        "company_name": "Example GmbH", "email": "ada@example.com",
        "phone_number": "+49 030 012345", "language": "DE",
    }


def test_order_lookup_maps_sql_aliases_and_preserves_text_and_components():
    row = order_row()
    result, cursor = lookup(row)

    assert result["success"] is True
    data = result["data"]
    assert data["order_number"] == "RA171165"
    assert data["document_type"] == "R"
    assert data["date_created"] == row["date_created"]
    assert data["date"] == data["date_created"]
    assert data["country"] == "DE"
    assert data["final_price"] == 1507.02
    assert data["customer_name"] == "Ada Example"
    for field in TEXT_FIELDS:
        assert data[field] == row[field]
    assert data["items"][0]["components"][0]["sku"] == "CP001"
    query, parameters = cursor.execute.call_args_list[0].args
    assert "WHERE Belegnummer = %s" in query
    assert parameters == ("RA171165",)
    assert cursor.execute.call_args_list[1].args[1] == ("RA171165",)


@pytest.mark.parametrize("value", [None, "", 0, 123456])
def test_order_lookup_returns_optional_fields_as_text_or_null(value):
    row = order_row()
    row.update({field: value for field in TEXT_FIELDS})
    row.update(date_created=None, price=None, country=None)

    result, _ = lookup(row)

    assert result["success"] is True
    data = result["data"]
    for field in TEXT_FIELDS:
        assert data[field] == (None if value is None else str(value))
    assert data["date_created"] is None
    assert data["final_price"] is None
    assert data["country"] is None


def test_missing_order_keeps_not_found_behavior():
    result, cursor = lookup(None)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"
    assert cursor.execute.call_count == 1
