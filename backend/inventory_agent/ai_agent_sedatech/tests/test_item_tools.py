from datetime import date
import json

import pytest
from pydantic import ValidationError

from tools.factory import build_tool_registry
from tools.items.analyse_items_used import (
    AnalyseItemsUsedArguments,
    create_analyse_items_used_handler,
)
from tools.items.search_items_skus import (
    SearchItemsSkusArguments,
    create_search_items_skus_handler,
)


class StubItemService:
    def __init__(self) -> None:
        self.requested_skus = None
        self.analysis_filters = None
        self.sales_rows = [
            {"sku": "ME00001", "name": "32GB RAM", "period": "2026-01-01", "sold_amount": 12},
            {"sku": "ME00001", "name": "32GB RAM", "period": "2026-02-01", "sold_amount": 4},
        ]

    def search_items_skus(self, list_of_skus):
        self.requested_skus = list_of_skus
        return {"CP00001": 7, "ME00001": 0}

    def analyse_items_used(self, **filters):
        self.analysis_filters = filters
        return self.sales_rows


def test_exact_sku_lookup_preserves_zero_and_identifies_unknown_skus() -> None:
    service = StubItemService()
    handler = create_search_items_skus_handler(service)

    result = handler(list_of_skus=[" CP00001 ", "ME00001", "CP00001", "UNKNOWN"])

    assert service.requested_skus == ["CP00001", "ME00001", "UNKNOWN"]
    assert result["requested_skus"] == service.requested_skus
    assert result["stock"] == {"CP00001": 7, "ME00001": 0}
    assert result["missing_skus"] == ["UNKNOWN"]


@pytest.mark.parametrize("skus", [[], [" "], ["x" * 101], ["SKU"] * 501, [42]])
def test_exact_sku_lookup_rejects_invalid_lists(skus) -> None:
    with pytest.raises(ValidationError):
        SearchItemsSkusArguments(list_of_skus=skus)


def test_sales_analysis_reuses_component_filters_and_forwards_dates() -> None:
    service = StubItemService()
    handler = create_analyse_items_used_handler(service)

    result = handler(
        date_from="2026-01-01",
        date_to="2026-02-28",
        ram_capacity=32,
        ram_ddr=5,
    )

    assert service.analysis_filters["category"] == "ME"
    assert service.analysis_filters["ram_capacity"] == 32
    assert service.analysis_filters["ram_ddr"] == 5
    assert service.analysis_filters["date_from"] == date(2026, 1, 1)
    assert service.analysis_filters["date_to"] == date(2026, 2, 28)
    assert service.analysis_filters["group_by"] == "month"
    assert "chart_type" not in service.analysis_filters
    assert result["date_from"] == "2026-01-01"
    assert result["date_to"] == "2026-02-28"
    assert result["requested_filters"] == {"category": "ME", "ram_capacity": 32, "ram_ddr": 5}
    assert result["rows"] == service.sales_rows
    assert result["row_count"] == 2
    assert "chart" not in result
    json.dumps(result)


@pytest.mark.parametrize(
    "arguments",
    [
        {"sku": "ME00001"},
        {"date_from": "2026-01-01", "date_to": "2026-02-28"},
        {"sku": "ME00001", "date_from": "2026-02-28", "date_to": "2026-01-01"},
        {"sku": "ME00001", "date_from": "2026-01-01", "date_to": "2026-02-28", "group_by": "quarter"},
        {"category": "CP", "ram_capacity": 32, "date_from": "2026-01-01", "date_to": "2026-02-28"},
        {"gpu_model": "RTX5070Ti", "date_from": "2026-01-01", "date_to": "2026-02-28"},
    ],
)
def test_sales_analysis_rejects_missing_dates_and_invalid_filters(arguments) -> None:
    with pytest.raises(ValidationError):
        AnalyseItemsUsedArguments(**arguments)


@pytest.mark.parametrize("group_by", ["day", "week", "month", "year", "total"])
def test_sales_analysis_accepts_single_day_and_supported_groupings(group_by) -> None:
    arguments = AnalyseItemsUsedArguments(
        sku="ME00001", date_from="2026-02-28", date_to="2026-02-28", group_by=group_by
    )

    assert arguments.date_from == arguments.date_to
    assert arguments.group_by == group_by


def test_sales_analysis_empty_results_remain_empty() -> None:
    service = StubItemService()
    service.sales_rows = []

    result = create_analyse_items_used_handler(service)(
        sku="ME00001", date_from="2026-01-01", date_to="2026-02-28", chart_type="line"
    )

    assert result["row_count"] == 0
    assert result["rows"] == []
    assert "chart" not in result


def test_sales_analysis_builds_graph_without_dropping_rows() -> None:
    service = StubItemService()
    service.sales_rows = [
        {"sku": f"ME{number:05d}", "name": "RAM", "period": "2026-01-01", "sold_amount": number}
        for number in range(125)
    ]

    result = create_analyse_items_used_handler(service)(
        category="ME", date_from="2026-01-01", date_to="2026-02-28", chart_type="line"
    )

    assert "chart_type" not in service.analysis_filters
    assert "chart_type" not in result["requested_filters"]
    assert result["chart"]["type"] == "line"
    assert result["chart"]["x_type"] == "temporal"
    assert len(result["chart"]["data"]) == 125
    assert result["chart"]["data"][-1] == {"x": "2026-01-01", "y": 124, "series": "ME00124 - RAM"}
    json.dumps(result)


def test_sales_totals_use_skus_as_chart_categories() -> None:
    service = StubItemService()
    service.sales_rows = [{"sku": "1234", "name": "RAM", "period": None, "sold_amount": 12}]

    result = create_analyse_items_used_handler(service)(
        sku="1234", date_from="2026-01-01", date_to="2026-02-28", group_by="total", chart_type="bar"
    )

    assert result["chart"]["x_type"] == "category"
    assert result["chart"]["x_label"] == "SKU / Article name"
    assert result["chart"]["data"] == [{"x": "1234 - RAM", "y": 12, "series": "1234 - RAM"}]


def test_factory_registers_both_tools_with_item_service_and_preserves_inventory_search() -> None:
    service = StubItemService()
    registry = build_tool_registry(order_service=object(), item_service=service)
    schemas = {schema["function"]["name"]: schema["function"] for schema in registry.schemas()}

    assert "search_item" in schemas
    sku_schema = schemas["search_items_skus"]["parameters"]
    assert sku_schema["required"] == ["list_of_skus"]
    assert sku_schema["properties"]["list_of_skus"]["minItems"] == 1
    assert sku_schema["properties"]["list_of_skus"]["maxItems"] == 500
    analysis_schema = schemas["analyse_items_used"]["parameters"]
    assert set(analysis_schema["required"]) == {"date_from", "date_to"}
    assert analysis_schema["properties"]["date_from"]["format"] == "date"
    assert analysis_schema["properties"]["group_by"]["default"] == "month"
    assert "ram_capacity" in analysis_schema["properties"]
    assert "chart_type" in analysis_schema["properties"]

    stock_result = registry.execute("search_items_skus", {"list_of_skus": [" CP00001 ", "ME00001"]})
    assert stock_result["success"] is True
    assert stock_result["data"]["missing_skus"] == []
    sales_result = registry.execute(
        "analyse_items_used", {"category": "ME", "date_from": "2026-01-01", "date_to": "2026-02-28"}
    )
    assert sales_result["success"] is True
    assert sales_result["data"]["row_count"] == 2


def test_new_tools_are_unavailable_without_item_service() -> None:
    registry = build_tool_registry(order_service=object())
    names = {schema["function"]["name"] for schema in registry.schemas()}

    assert "search_items_skus" not in names
    assert "analyse_items_used" not in names


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("search_items_skus", {"list_of_skus": [" "]}),
        ("analyse_items_used", {"sku": "ME00001", "date_from": "2026-02-28", "date_to": "2026-01-01"}),
    ],
)
def test_registry_validates_before_new_tools_reach_service(tool_name, arguments) -> None:
    service = StubItemService()
    registry = build_tool_registry(order_service=object(), item_service=service)

    result = registry.execute(tool_name, arguments)

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert service.requested_skus is None
    assert service.analysis_filters is None
