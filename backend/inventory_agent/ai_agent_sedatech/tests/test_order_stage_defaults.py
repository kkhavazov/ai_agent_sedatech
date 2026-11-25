from datetime import date
from unittest.mock import Mock

import pytest

from repositories.sqlserver_order_repository import SqlServerOrderRepository
from services.order_service import OrderService
from tools.factory import build_tool_registry


@pytest.mark.parametrize("tool_name", ["filter_orders", "count_orders"])
@pytest.mark.parametrize("arguments, expected_parameters", [
    ({}, ("R",)),
    ({"date_from": "2026-11-01"}, ("R", date(2026, 11, 1))),
    ({"status": "0"}, ("R", "0")),
    ({"document_type": None}, ("R",)),
    ({"document_type": " "}, ("R",)),
    ({"document_type": "D"}, ("D",)),
    ({"document_type": "L", "status": "2"}, ("L", "2")),
    ({"lifecycle_state": "confirmed_workshop"}, ("D", "0")),
    ({"lifecycle_state": "in_production"}, ("L", "0")),
    ({"lifecycle_state": "ready_or_sent"}, ("R", "0")),
])
def test_order_tools_apply_stage_filters_to_sql(tool_name, arguments, expected_parameters):
    cursor = Mock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = {"OrderCount": 7}
    repository = SqlServerOrderRepository("server", "user", "password", "database")
    repository._connect = Mock()
    repository._connect.return_value.cursor.return_value = cursor
    registry = build_tool_registry(OrderService(repository))

    result = registry.execute(tool_name, arguments)

    assert result["success"] is True, result
    query, parameters = cursor.execute.call_args.args
    assert "Belegtyp = %s" in query
    assert parameters == expected_parameters
    if tool_name == "filter_orders":
        assert result["data"]["resolved_database_filters"]["document_type"] == expected_parameters[0]
    else:
        assert result["data"] == 7


@pytest.mark.parametrize("tool_name", ["filter_orders", "count_orders"])
def test_explicit_stage_conflicts_still_fail_validation(tool_name):
    repository = Mock()
    result = build_tool_registry(OrderService(repository)).execute(tool_name, {
        "lifecycle_state": "in_production", "document_type": "R",
    })
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    repository.filter_orders.assert_not_called()
    repository.count_orders.assert_not_called()
