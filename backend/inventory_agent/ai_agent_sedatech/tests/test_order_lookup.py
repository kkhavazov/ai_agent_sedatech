from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from repositories.sqlserver_order_repository import SqlServerOrderRepository
from services.order_service import OrderService
from tools.order_tools import build_get_order_tool
from tools.orders.filter_orders import create_filter_orders_handler
from tools.registry import ToolRegistry


TEXT_FIELDS = (
    "tax_number", "tracking_number", "company_name", "email",
    "phone_number", "language", "platform", "order_number",
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
        "selling_price": Decimal("1507.02"),
        "production_cost": Decimal("1000.10"),
        "gross_profit": Decimal("266.30"),
        "tracking_number": "001234567890", "tax_number": "DE001234567",
        "company_name": "Example GmbH", "email": "ada@example.com",
        "phone_number": "+49 030 012345", "language": "DE",
        "platform": "Amazon",
        "order_number": "001-1234567-1234567",
    }


def test_order_lookup_maps_sql_aliases_and_preserves_text_and_components():
    row = order_row()
    result, cursor = lookup(row)

    assert result["success"] is True
    data = result["data"]
    assert data["document_number"] == "RA171165"
    assert data["order_number"] != data["document_number"]
    assert data["order_number"] != data["tracking_number"]
    assert data["document_type"] == "R"
    assert data["date_created"] == row["date_created"]
    assert data["date"] == data["date_created"]
    assert data["country"] == "DE"
    assert data["final_price"] == 1507.02
    assert data["selling_price"] == 1507.02
    assert data["production_cost"] == 1000.10
    assert data["gross_profit"] == 266.30
    assert data["customer_name"] == "Ada Example"
    for field in TEXT_FIELDS:
        assert data[field] == row[field]
    assert data["items"][0]["components"][0]["sku"] == "CP001"
    query, parameters = cursor.execute.call_args_list[0].args
    assert "WHERE t1.Belegnummer = %s" in query
    assert "t1.Name," in query
    assert "t2.Name AS platform" in query
    assert "t1._TRACKING AS tracking_number" in query
    assert "t1.IhrAuftrag AS order_number" in query
    assert "t1.EuroBrutto AS selling_price" in query
    assert "t1.UebernahmeOffen AS production_cost" in query
    assert "t1.ErloesEuro AS gross_profit" in query
    assert "LEFT JOIN dbo.MITARBW AS t2 ON t1.Vertreter = t2.Nr" in query
    assert parameters == ("RA171165",)
    assert cursor.execute.call_args_list[1].args[1] == ("RA171165",)


@pytest.mark.parametrize("value", [None, "", 0, 123456])
def test_order_lookup_returns_optional_fields_as_text_or_null(value):
    row = order_row()
    row.update({field: value for field in TEXT_FIELDS})
    row.update(date_created=None, selling_price=None, production_cost=None, gross_profit=None, country=None)

    result, _ = lookup(row)

    assert result["success"] is True
    data = result["data"]
    assert data["document_number"] == "RA171165"
    for field in TEXT_FIELDS:
        assert data[field] == (None if value is None else str(value))
    assert data["date_created"] is None
    assert data["final_price"] is None
    assert data["selling_price"] is None
    assert data["production_cost"] is None
    assert data["gross_profit"] is None
    assert data["country"] is None


def test_missing_order_keeps_not_found_behavior():
    result, cursor = lookup(None)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"
    assert cursor.execute.call_count == 1


@pytest.mark.parametrize("external_reference", ["001-1234567-1234567", None])
def test_filtered_order_can_be_looked_up_by_document_number(external_reference):
    row = order_row()
    row["order_number"] = external_reference
    cursor = Mock()
    cursor.fetchall.side_effect = [[{
        "DocumentNumber": "RA171165", "OrderNumber": external_reference,
        "DocumentType": "R", "OrderStatus": 0,
        "CreationDate": row["date_created"], "CustomerName": "Ada Example",
        "Country": "DE", "Address": "Example Street",
        **{key: row[key] for key in ("selling_price", "production_cost", "gross_profit")},
    }], []]
    cursor.fetchone.return_value = row
    connection = Mock()
    connection.cursor.return_value = cursor
    repository = SqlServerOrderRepository("server", "user", "password", "database")
    repository._connect = Mock(return_value=connection)
    service = OrderService(repository)

    filtered = create_filter_orders_handler(service)(document_type="R", limit=1)
    document = filtered["orders"][0]
    assert document["document_number"] == "RA171165"
    assert document["order_number"] == external_reference
    assert document["selling_price"] == document["final_price"] == 1507.02
    assert document["production_cost"] == 1000.10
    assert document["gross_profit"] == 266.30
    query = cursor.execute.call_args_list[0].args[0]
    assert "Belegnummer AS DocumentNumber" in query
    assert "IhrAuftrag AS OrderNumber" in query
    assert "EuroBrutto AS selling_price" in query
    assert "UebernahmeOffen AS production_cost" in query
    assert "ErloesEuro AS gross_profit" in query

    result = build_get_order_tool(service).handler(
        order_number=document["document_number"]
    )
    assert result["document_number"] == "RA171165"
    assert result["order_number"] == external_reference
    assert cursor.execute.call_args_list[1].args[1] == ("RA171165",)
    assert cursor.execute.call_args_list[2].args[1] == ("RA171165",)
