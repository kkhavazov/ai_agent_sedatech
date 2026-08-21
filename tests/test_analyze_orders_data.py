from datetime import date, datetime

from services.order_service import OrderService
from tools.factory import build_tool_registry
from tools.orders.analyze_orders import create_analyze_orders_data_handler


class AnalyzeRepository:
    def __init__(self) -> None:
        self.arguments = {}

    def analyze_orders_data(self, **arguments):
        self.arguments = arguments
        return FakeDataFrame(
            [{
                "CreatedAt": datetime(2026, 8, 21, 12, 30),
                "FinalPrice": 1499.0,
                "Country": "DE",
            }]
        )


class FakeDataFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, *, orient):
        assert orient == "records"
        return self.records


def test_analyze_handler_serializes_dataframe() -> None:
    repository = AnalyzeRepository()
    handler = create_analyze_orders_data_handler(OrderService(repository))

    result = handler(
        date_from=date(2026, 8, 1),
        document_type="R",
        max_rows=50,
    )

    assert result["row_count"] == 1
    assert result["possibly_truncated"] is False
    assert result["rows"][0]["CreatedAt"] == "2026-08-21T12:30:00"
    assert repository.arguments["document_type"] == "R"


def test_analyze_tool_is_registered() -> None:
    repository = AnalyzeRepository()
    registry = build_tool_registry(OrderService(repository))

    tool_names = [schema["function"]["name"] for schema in registry.schemas()]

    assert "analyze_orders_data" in tool_names
