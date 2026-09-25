from datetime import date
from decimal import Decimal
import re

import pandas as pd
import pymssql
import pytest

from repositories.sqlserver_item_repository import SqlServerItemRepository
from services.item_service import ItemService


class RecordingCursor:
    def __init__(self, rows, error=None):
        self.rows = rows
        self.error = error
        self.query = ""
        self.parameters = ()
        self.closed = False

    def execute(self, query, parameters=()):
        self.query = query
        self.parameters = parameters
        if self.error is not None:
            raise self.error

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class RecordingConnection:
    def __init__(self, rows, error=None):
        self.recording_cursor = RecordingCursor(rows, error)
        self.closed = False

    def cursor(self):
        return self.recording_cursor

    def close(self):
        self.closed = True


def make_repository(rows=(), error=None):
    repository = SqlServerItemRepository("server", "user", "password", "database")
    connection = RecordingConnection(rows, error)
    repository._connect = lambda: connection
    return repository, connection, connection.recording_cursor


def test_single_sku_stock_lookup_uses_parameter_and_dictionary_row():
    repository, connection, cursor = make_repository([
        {"Artikelnummer": "CP00001", "CurrentStock": Decimal("12")},
    ])

    assert repository.search_items_skus(["CP00001"]) == {"CP00001": 12}
    assert re.search(r"\bIN\s*\(\s*%s\s*\)", cursor.query, re.IGNORECASE)
    assert cursor.parameters == ("CP00001",)
    assert "CP00001" not in cursor.query
    assert cursor.closed and connection.closed


def test_stock_lookup_normalizes_deduplicates_and_keeps_sql_literal_in_parameters():
    unusual_sku = "CP' OR 1=1 --"
    repository, _, cursor = make_repository([
        {"Artikelnummer": "CP00001", "CurrentStock": 2},
        {"Artikelnummer": unusual_sku, "CurrentStock": 3},
    ])

    result = repository.search_items_skus([
        " CP00001 ", "CP00001", unusual_sku,
    ])

    assert result == {"CP00001": 2, unusual_sku: 3}
    assert cursor.parameters == ("CP00001", unusual_sku)
    assert cursor.query.count("%s") == 2
    assert unusual_sku not in cursor.query


def test_stock_lookup_retains_zero_and_requested_spelling_while_omitting_unknown():
    repository, _, cursor = make_repository([
        {"Artikelnummer": "CP00001", "CurrentStock": 0},
        {"Artikelnummer": "ME00002", "CurrentStock": Decimal("6")},
    ])

    result = repository.search_items_skus(["cp00001", "me00002", "UNKNOWN"])

    assert result == {"cp00001": 0, "me00002": 6}
    assert "LEFT JOIN" in " ".join(cursor.query.upper().split())
    assert not re.search(r"LAGERP\.Bestand\s*>\s*0", cursor.query, re.IGNORECASE)


def test_empty_sku_lookup_never_opens_database(monkeypatch):
    repository, _, _ = make_repository()
    monkeypatch.setattr(repository, "_connect", lambda: pytest.fail("No database needed"))

    assert repository.search_items_skus([]) == {}


@pytest.mark.parametrize("operation", ["stock", "sales"])
def test_database_failure_closes_resources_and_propagates_error(operation):
    repository, connection, cursor = make_repository(
        error=pymssql.OperationalError("database unavailable"),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        if operation == "stock":
            repository.search_items_skus(["CP00001"])
        else:
            repository.analyse_items_used(
                date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
            )

    assert cursor.closed and connection.closed


def test_sales_query_aggregates_invoice_components_daily_without_current_stock():
    day = date(2026, 1, 31)
    repository, connection, cursor = make_repository([
        {"SKU": "ME00001", "Name": "16GB DDR5", "SoldAmount": Decimal("2.5"), "Dates": day},
    ])

    result = repository.analyse_items_used(
        date_from=date(2026, 1, 1), date_to=day,
        sku="ME00001", category="ME", ram_capacity=16, ram_ddr=5,
    )

    assert list(result.columns) == ["SKU", "Name", "SoldAmount", "Dates"]
    assert result.to_dict("records") == [
        {"SKU": "ME00001", "Name": "16GB DDR5", "SoldAmount": Decimal("2.5"), "Dates": day},
    ]
    query = " ".join(cursor.query.split())
    assert "SUM(BELEGP.Menge)" in query
    assert re.search(r"CAST\(BELEGP\.Datum AS date\)", query, re.IGNORECASE)
    assert "BELEGP.Belegtyp = 'R'" in query
    assert re.search(r"ART\.Artikelgruppe IN", query, re.IGNORECASE)
    assert "GROUP BY" in query.upper()
    assert "ART.Artikelnummer LIKE %s" in query
    assert "BELEGP.Datum >= %s" in query
    assert "BELEGP.Datum < DATEADD(day, 1, %s)" in query
    assert "SERIE" not in query.upper()
    assert "LAGERP" not in query.upper()
    assert "AngelegtAm" not in query
    for value in ("%ME00001%", "%ME%", "16GB%", "%DDR5%", date(2026, 1, 1), day):
        assert value in cursor.parameters
    assert query.count("%s") == len(cursor.parameters)
    assert cursor.closed and connection.closed


def test_sales_repository_returns_empty_frame_with_expected_columns():
    repository, connection, cursor = make_repository([])

    result = repository.analyse_items_used(
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
    )

    assert result.empty
    assert list(result.columns) == ["SKU", "Name", "SoldAmount", "Dates"]
    assert cursor.closed and connection.closed


class StubItemRepository:
    def __init__(self, sales_rows=()):
        self.sales_rows = sales_rows
        self.calls = []

    def search_items_skus(self, list_of_skus):
        self.calls.append(list_of_skus)
        return {sku: 4 for sku in list_of_skus}

    def analyse_items_used(self, **arguments):
        self.calls.append(arguments)
        return pd.DataFrame.from_records(
            self.sales_rows, columns=["SKU", "Name", "SoldAmount", "Dates"],
        )


def test_stock_service_normalizes_and_deduplicates_skus():
    repository = StubItemRepository()

    result = ItemService(repository).search_items_skus([" CP00001 ", "CP00001", "ME00001"])

    assert result == {"CP00001": 4, "ME00001": 4}
    assert repository.calls == [["CP00001", "ME00001"]]


def test_stock_service_empty_list_returns_without_query():
    repository = StubItemRepository()

    assert ItemService(repository).search_items_skus([]) == {}
    assert repository.calls == []


@pytest.mark.parametrize("skus", [[" "], ["CP00001", ""], [123], [f"CP{i}" for i in range(501)]])
def test_stock_service_rejects_invalid_input_before_query(skus):
    repository = StubItemRepository()

    with pytest.raises(ValueError):
        ItemService(repository).search_items_skus(skus)

    assert repository.calls == []


@pytest.mark.parametrize(
    ("group_by", "expected"),
    [
        ("day", {
            ("CP1", "2025-12-31"): 2.5, ("CP1", "2026-01-04"): -0.5,
            ("CP1", "2026-01-05"): 4, ("CP1", "2027-01-05"): 3,
            ("CP2", "2026-01-04"): 8,
        }),
        ("week", {
            ("CP1", "2025-12-29"): 2, ("CP1", "2026-01-05"): 4,
            ("CP1", "2027-01-04"): 3, ("CP2", "2025-12-29"): 8,
        }),
        ("month", {
            ("CP1", "2025-12-01"): 2.5, ("CP1", "2026-01-01"): 3.5,
            ("CP1", "2027-01-01"): 3, ("CP2", "2026-01-01"): 8,
        }),
        ("year", {
            ("CP1", "2025-01-01"): 2.5, ("CP1", "2026-01-01"): 3.5,
            ("CP1", "2027-01-01"): 3, ("CP2", "2026-01-01"): 8,
        }),
        ("total", {("CP1", None): 9, ("CP2", None): 8}),
    ],
)
def test_sales_service_groups_components_across_years_and_keeps_fractional_returns(group_by, expected):
    repository = StubItemRepository([
        {"SKU": "CP1", "Name": "Processor", "SoldAmount": Decimal("2.5"), "Dates": date(2025, 12, 31)},
        {"SKU": "CP1", "Name": "Processor", "SoldAmount": Decimal("-0.5"), "Dates": date(2026, 1, 4)},
        {"SKU": "CP1", "Name": "Processor", "SoldAmount": Decimal("4"), "Dates": date(2026, 1, 5)},
        {"SKU": "CP1", "Name": "Processor", "SoldAmount": Decimal("3"), "Dates": date(2027, 1, 5)},
        {"SKU": "CP2", "Name": "Processor", "SoldAmount": Decimal("8"), "Dates": date(2026, 1, 4)},
    ])

    result = ItemService(repository).analyse_items_used(
        date_from=date(2025, 12, 1), date_to=date(2027, 1, 31), group_by=group_by,
        category="CP",
    )

    assert {(row["sku"], row["period"]): row["sold_amount"] for row in result} == expected
    assert len(result) == len(expected)
    assert all(row["name"] == "Processor" for row in result)
    assert all(set(row) == {"sku", "name", "period", "sold_amount"} for row in result)


def test_sales_service_defaults_to_month_and_forwards_component_filters():
    repository = StubItemRepository([
        {"SKU": "GC1", "Name": "Graphics card", "SoldAmount": 5, "Dates": date(2026, 1, 15)},
    ])
    arguments = {
        "date_from": date(2026, 1, 1), "date_to": date(2026, 1, 31),
        "category": "GC", "gpu_manufacturer": "NVIDIA", "gpu_vram": 16,
    }

    result = ItemService(repository).analyse_items_used(**arguments)

    assert result == [{"sku": "GC1", "name": "Graphics card", "period": "2026-01-01", "sold_amount": 5}]
    assert len(repository.calls) == 1
    assert all(repository.calls[0][key] == value for key, value in arguments.items())
    assert "group_by" not in repository.calls[0]


@pytest.mark.parametrize("group_by", ["day", "week", "month", "year", "total"])
def test_sales_service_empty_data_returns_empty_list(group_by):
    result = ItemService(StubItemRepository()).analyse_items_used(
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), group_by=group_by,
        category="CP",
    )

    assert result == []


@pytest.mark.parametrize("overrides", [
    {"date_from": date(2026, 2, 1)},
    {"date_from": None},
    {"date_to": None},
    {"group_by": "quarter"},
])
def test_sales_service_rejects_invalid_date_range_or_group_before_query(overrides):
    repository = StubItemRepository()
    arguments = {
        "date_from": date(2026, 1, 1), "date_to": date(2026, 1, 31),
        "category": "CP", **overrides,
    }

    with pytest.raises(ValueError):
        ItemService(repository).analyse_items_used(**arguments)

    assert repository.calls == []
