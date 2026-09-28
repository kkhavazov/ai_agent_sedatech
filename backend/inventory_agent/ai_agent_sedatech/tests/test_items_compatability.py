import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

# Load this SQL adapter independently of optional agent/model dependencies.
spec = importlib.util.spec_from_file_location(
    "compatability_repository",
    Path(__file__).parents[1] / "repositories" / "sqlserver_items_compatability_repository.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def repository():
    return module.SqlServerItemsCompatabilityRepository("server", "user", "password", "db")


def test_variable_predicates_are_parameterized_and_deduplicated():
    predicate, values = module.build_sku_conditions([" PS00141a ", "TW00269", "PS00141a", "x' OR 1=1 --"])
    assert predicate == "(%s, %s, %s)"
    assert values == ("PS00141a", "TW00269", "x' OR 1=1 --")
    assert "OR 1=1" not in predicate
    predicate, values = module.build_sku_conditions([f"SKU{i}" for i in range(60)])
    assert len(values) == predicate.count("%s") == 60


@pytest.mark.parametrize("skus, expected", [
    (["A"], ["1", "2", "3"]),
    (["A", "B"], ["1", "2"]),
    (["A", "B", "C"], ["1"]),
    ([" A ", "B", "A"], ["1", "2"]),
    (["unknown"], []),
    (["x' OR 1=1 --"], []),
    ([f"SKU{i}" for i in range(60)], []),
])
def test_grouped_query_requires_all_unique_skus(skus, expected):
    # Execute the generated standard SQL locally; only driver placeholders differ.
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE BELEGP (Belegnummer TEXT, Artikelnummer TEXT)")
        connection.executemany("INSERT INTO BELEGP VALUES (?, ?)", [
            ("1", "A"), ("1", "A"), ("1", "B"), ("1", "C"), ("1", "extra"),
            ("2", "A"), ("2", "B"), ("3", "A"), ("3", "A"),
        ])
        conditions, values = module.build_sku_conditions(skus)
        query = repository()._build_query(conditions)
        cursor = connection.execute(query.replace("%s", "?"), (*values, len(values)))
        assert cursor.description[0][0] == "order_number"
        assert sorted(row[0] for row in cursor.fetchall()) == expected
    finally:
        connection.close()


@pytest.mark.parametrize("skus", [[], "SKU", [""], ["  "], [None], [123]])
def test_invalid_skus(skus):
    with pytest.raises(ValueError):
        module.build_sku_conditions(skus)


def test_empty_query_does_not_connect():
    repo = repository()
    repo._connect = Mock()
    repo._build_query = Mock(return_value="")
    with pytest.raises(NotImplementedError, match="QUERY_NOT_CONFIGURED"):
        repo.items_compatability(["A", "B"])
    repo._connect.assert_not_called()


def test_count_distinct_orders_and_limit_sample():
    repo = repository()
    repo._build_query = Mock(return_value="user supplied query")
    cursor = Mock()
    cursor.fetchmany.side_effect = [
        [{"order_number": "001"}, {"order_number": "001"}],
        [{"order_number": "002"}, {"order_number": "003"}], [],
    ]
    connection = Mock()
    connection.cursor.return_value = cursor
    repo._connect = Mock(return_value=connection)
    assert repo.items_compatability(["A", "B"], sample_limit=1) == {
        "skus": ["A", "B"], "matching_order_count": 3,
        "sample_order_numbers": ["001"], "order_numbers_truncated": True,
    }
    cursor.execute.assert_called_once_with("user supplied query", ("A", "B", 2))
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("rows", [[], [{"order_number": "1"}]])
def test_zero_sample_limit(rows):
    repo = repository()
    repo._build_query = Mock(return_value="query")
    connection = Mock()
    cursor = connection.cursor.return_value
    cursor.fetchmany.side_effect = [rows, []]
    repo._connect = Mock(return_value=connection)
    result = repo.items_compatability(["A"], sample_limit=0)
    assert result["matching_order_count"] == len(rows)
    assert result["sample_order_numbers"] == []
    assert result["order_numbers_truncated"] is bool(rows)


def test_database_failure_closes_resources():
    repo = repository()
    repo._build_query = Mock(return_value="query")
    connection = Mock()
    cursor = connection.cursor.return_value
    cursor.execute.side_effect = RuntimeError("Database unavailable")
    repo._connect = Mock(return_value=connection)
    with pytest.raises(RuntimeError, match="Database unavailable"):
        repo.items_compatability(["A"])
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
