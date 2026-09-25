import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from langchain_core.messages import HumanMessage, ToolMessage


class SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


@pytest.fixture
def support_module():
    with patch("qdrant_client.QdrantClient"), patch("ollama.Client"):
        import customer_support_agent
    return customer_support_agent


@pytest.fixture
def chart_app(support_module):
    # Import the real renderer without starting a chat or external service.
    path = Path(__file__).parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("component_chart_app", path)
    module = importlib.util.module_from_spec(spec)
    with (
        patch("streamlit.title"),
        patch("streamlit.session_state", SessionState()),
        patch("streamlit.chat_input", return_value=None),
    ):
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def component_chart():
    return {
        "type": "line",
        "title": "Component sales",
        "x_label": "Month",
        "y_label": "Units sold",
        "x_type": "temporal",
        "data": [
            {"x": "2026-02", "y": 7.0, "series": "ME-001"},
            {"x": "2026-01", "y": 3.0, "series": "ME-001"},
            {"x": "2026-01", "y": 5.0, "series": "ME-002"},
        ],
    }


def test_component_chart_reaches_streamlit_from_inventory(
    support_module, chart_app, component_chart, monkeypatch
):
    request = "Graph monthly sales of ME-001 and ME-002 in 2026."
    agent_result = SimpleNamespace(
        draft="Component sales are shown below.",
        model_name="test",
        tool_calls=[{"name": "analyse_items_used", "arguments": {}}],
        tool_results=[{
            "success": True,
            "tool": "analyse_items_used",
            "data": {"chart": component_chart},
            "error": None,
        }],
        warnings=[],
    )
    requests = []

    def handle_request(text):
        requests.append(text)
        return agent_result

    monkeypatch.setattr(
        support_module, "_get_inventory_agent",
        lambda: SimpleNamespace(handle_request=handle_request),
    )
    monkeypatch.setattr(support_module, "_check_sql_dns", lambda: None)

    payload = support_module.query_inventory.invoke({"request": request})
    assert requests == [request]
    result = {"messages": [
        HumanMessage(content=request),
        ToolMessage(
            content=json.dumps(payload), name="query_inventory", tool_call_id="1"
        ),
    ]}
    extracted = chart_app.extract_analysis_chart(result, request)
    assert extracted == component_chart
    with patch.object(chart_app.st, "line_chart") as render, patch.object(chart_app.st, "caption"):
        chart_app.render_chart(extracted)
    frame = render.call_args.args[0]
    assert frame["x_date"].tolist() == list(pd.to_datetime([
        "2026-01-01", "2026-01-01", "2026-02-01"
    ]))
    assert render.call_args.kwargs["color"] == "series"
    assert set(frame["series"]) == {"ME-001", "ME-002"}


def test_prior_turn_chart_is_not_reused(chart_app, component_chart):
    result = {"messages": [
        HumanMessage(content="Graph component sales"),
        ToolMessage(
            content=json.dumps({"chart": component_chart}),
            name="query_inventory", tool_call_id="old",
        ),
        HumanMessage(content="Graph sales of an unknown SKU"),
        ToolMessage(
            content=json.dumps({"answer": "No matching sales."}),
            name="query_inventory", tool_call_id="new",
        ),
    ]}
    assert chart_app.extract_analysis_chart(result, "Graph sales of an unknown SKU") is None


def test_chart_followup_does_not_need_another_graph_keyword(chart_app, component_chart):
    result = {"messages": [
        HumanMessage(content="Use months instead"),
        ToolMessage(
            content=json.dumps({"chart": component_chart}),
            name="query_inventory", tool_call_id="1",
        ),
    ]}
    assert chart_app.extract_analysis_chart(result, "Use months instead") == component_chart


def test_total_chart_keeps_numeric_sku_as_category(chart_app):
    chart = {
        "type": "bar",
        "x_type": "category",
        "data": [{"x": "2026", "y": 5.0, "series": None}],
    }
    with patch.object(chart_app.st, "bar_chart") as render:
        chart_app.render_chart(chart)
    assert render.call_args.kwargs["x"] == "x"
    assert render.call_args.args[0]["x"].tolist() == ["2026"]


def test_existing_order_chart_fallback_remains_available(chart_app):
    result = {"messages": [
        HumanMessage(content="Graph orders monthly"),
        ToolMessage(
            content=json.dumps({"answer": [{"year": 2026, "month": 1, "order_count": 4}]}),
            name="analyze_data", tool_call_id="1",
        ),
    ]}
    chart = chart_app.extract_analysis_chart(result, "Graph orders monthly")
    assert chart["data"] == [{"x": "Jan 2026", "y": 4.0, "series": None}]
