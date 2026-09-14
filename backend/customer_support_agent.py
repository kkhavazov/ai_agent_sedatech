import ast
import json
import logging
import queue
import socket
import sys
import threading
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.tools import tool
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model
from langchain_experimental.agents.agent_toolkits import (
    create_pandas_dataframe_agent,
)
from langchain_experimental.tools.python.tool import PythonAstREPLTool
from pydantic import BaseModel, Field

from llm_requests import Conversation, OLLAMA_ADDRESS


logger = logging.getLogger(__name__)

from langchain_ollama import ChatOllama

model = ChatOllama(
    base_url=OLLAMA_ADDRESS,
    model="qwen3.5:9b", 
    temperature=0,
    # Retrieved tickets and tool schemas need room alongside the final answer.
    num_ctx=16384,
    num_predict=2048,
)

#GEMINI
import os
from dotenv import load_dotenv

load_dotenv()

os.environ["GEMINI_API_KEY"]

# model = init_chat_model("google_genai:gemini-2.5-flash")


class ChartPoint(BaseModel):
    x: str = Field(description="Category or date shown on the x-axis")
    y: float = Field(description="Numeric value shown on the y-axis")
    series: str | None = Field(
        default=None,
        description="Optional series name when the chart has multiple series",
    )


class ChartArguments(BaseModel):
    chart_type: Literal["bar", "line", "area", "scatter"]
    title: str
    x_label: str
    y_label: str
    # Empty model-generated data must reach the handler so the deterministic
    # temporal-chart fallback can run instead of aborting the whole agent.
    data: list[ChartPoint] = Field(max_length=100)


_SAFE_PYTHON_FUNCTIONS = {
    "abs": abs,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "sorted": sorted,
    "sum": sum,
}

_SAFE_PYTHON_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.Name, ast.Load, ast.Store,
    ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Subscript,
    ast.Slice, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.keyword, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq,
    ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


def _validate_python_calculation(code: str) -> None:
    """Reject Python features that could access the host or exhaust resources."""
    if len(code) > 2_000:
        raise ValueError("Python calculation is limited to 2,000 characters")

    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_PYTHON_NODES):
            raise ValueError(f"Python construct {type(node).__name__} is not allowed")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("Private names are not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct calls to approved functions are allowed")
            if node.func.id not in _SAFE_PYTHON_FUNCTIONS:
                raise ValueError(f"Function {node.func.id!r} is not allowed")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int) and abs(node.value) > 1_000_000_000:
                raise ValueError("Integer literals are limited to 1,000,000,000")
            if isinstance(node.value, (str, bytes)) and len(node.value) > 10_000:
                raise ValueError("String literals are limited to 10,000 characters")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if not (
                isinstance(node.right, ast.Constant)
                and isinstance(node.right.value, int)
                and abs(node.right.value) <= 100
            ):
                raise ValueError("Exponents must be integer literals between -100 and 100")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            operands = ((node.left, node.right), (node.right, node.left))
            for sequence, count in operands:
                if (
                    isinstance(sequence, (ast.List, ast.Tuple, ast.Set))
                    or isinstance(sequence, ast.Constant)
                    and isinstance(sequence.value, (str, bytes))
                ) and (
                    not isinstance(count, ast.Constant)
                    or not isinstance(count.value, int)
                    or count.value > 10_000
                ):
                    raise ValueError("Sequence repetition is limited to 10,000 items")


@tool
def run_python_calculation(code: str) -> dict:
    """Run a small, self-contained Python calculation. Use this for arithmetic,
    percentages, totals, comparisons, and sorting. The available functions are
    abs, len, max, min, round, sorted, and sum. Imports, attributes, file or
    network access, loops, function definitions, and private names are blocked.
    """
    try:
        _validate_python_calculation(code)
        repl = PythonAstREPLTool(
            globals={"__builtins__": {}},
            locals=dict(_SAFE_PYTHON_FUNCTIONS),
        )
        result = repl.invoke({"query": code})
        return {"answer": str(result)}
    except (SyntaxError, ValueError) as exc:
        return {
            "answer": "The calculation was rejected.",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }

@tool
def search_customer_kb(
    query: str,
    product_sku: str | None = None,
    status: str | None = None,
) -> dict:
    """Find relevant precedent tickets and their resolutions."""
    conversation = Conversation(
        product_sku=product_sku,
        status=status,
    )
    matches = conversation._retrieve(query)

    return {
        "answer": (
            "Relevant precedent tickets were found."
            if matches
            else "No relevant precedent tickets were found."
        ),
        "matches": matches,
        "source_ticket_ids": [
            match["ticket_id"] for match in matches
        ],
    }


@lru_cache(maxsize=1)
def _get_inventory_agent():
    """Build the cloned inventory agent once, on its first actual use."""
    project_dir = Path(__file__).parent / "inventory_agent" / "ai_agent_sedatech"
    if not project_dir.is_dir():
        raise RuntimeError(f"Inventory agent was not found at {project_dir}")

    # When the cloned project is imported from the backend, python-dotenv would
    # otherwise search the backend working directory and miss this file.
    load_dotenv(project_dir / ".env", override=False)

    # The cloned project uses top-level imports such as `from agent...`, so its
    # project root must be importable until those imports are made package-relative.
    project_dir_text = str(project_dir)
    if project_dir_text not in sys.path:
        sys.path.insert(0, project_dir_text)

    from factory import build_agent

    agent = build_agent()
    # A failed database tool should not cause ten LLM/tool retry rounds.
    agent.max_tool_rounds = int(os.getenv("INVENTORY_MAX_TOOL_ROUNDS", "3"))
    return agent


def _check_sql_dns(timeout_seconds: float = 5.0) -> str | None:
    """Return an error when SQL DNS cannot be resolved within a fixed bound."""
    if os.getenv("REPOSITORY_BACKEND", "demo") != "sqlserver":
        return None

    hostname = os.getenv("SQLSERVER_SERVER", "").split("\\", 1)[0]
    port = int(os.getenv("SQLSERVER_PORT", "1433"))
    if not hostname:
        return "SQLSERVER_SERVER is not configured"

    outcome: queue.Queue[str | None] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            outcome.put(None)
        except OSError as exc:
            outcome.put(f"SQL Server hostname could not be resolved: {exc}")

    worker = threading.Thread(target=resolve, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        return f"SQL Server DNS lookup exceeded {timeout_seconds:g} seconds"
    return outcome.get_nowait()


@tool
def query_inventory(request: str) -> dict:
    """Use the inventory agent for order status, order lifecycle, order counts,
    individual order details, item status, product availability, stock quantities,
    SKUs, cases, customers, missing components, or the current Berlin date/time.
    The inventory agent selects the appropriate specialized inventory tool. Pass
    the user's complete original question unchanged, preserving order numbers,
    product names, model numbers, and SKUs. Do not use analyze_data for
    these operational lookups.
    """
    try:
        inventory_agent = _get_inventory_agent()
        dns_error = _check_sql_dns()
        if dns_error:
            return {
                "answer": "Inventory service is currently unavailable.",
                "error": {
                    "type": "InventoryConnectionError",
                    "message": dns_error,
                },
            }
        result = inventory_agent.handle_request(request)
    except Exception as exc:
        return {
            "answer": "Inventory service is currently unavailable.",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    return {
        "answer": result.draft,
        "model": result.model_name,
        "tool_calls": result.tool_calls,
        "tool_results": result.tool_results,
        "warnings": result.warnings,
    }


def _infer_analysis_lifecycle(request: str) -> str | None:
    normalized = request.casefold()
    if "unconfirmed" in normalized:
        return "created_unconfirmed"
    if "currently in production" in normalized:
        return "in_production"
    if any(
        phrase in normalized
        for phrase in ("sent", "ready to ship", "ready for shipment")
    ):
        return "ready_or_sent"
    if "confirmed" in normalized:
        return "confirmed_workshop"
    return None


def _build_temporal_chart(frame, request: str) -> dict | None:
    """Build a reliable chart when the dataframe LLM omits create_chart."""
    normalized = request.casefold()
    if "CreatedAt" not in frame.columns:
        return None

    if any(word in normalized for word in ("week", "weekly")):
        frequency = "W-SUN"
        title = "Orders by week"
        x_label = "Week starting"
    elif any(word in normalized for word in ("day", "daily")):
        frequency = "D"
        title = "Orders by day"
        x_label = "Date"
    elif any(word in normalized for word in ("month", "monthly")):
        frequency = "M"
        title = "Orders by month"
        x_label = "Month"
    else:
        return None

    import pandas as pd

    dates = pd.to_datetime(frame["CreatedAt"], errors="coerce")
    valid_dates = dates.dropna()
    if valid_dates.empty:
        return None

    if frequency == "D":
        buckets = valid_dates.dt.normalize()
    else:
        buckets = valid_dates.dt.to_period(frequency).dt.start_time

    counts = buckets.value_counts().sort_index()
    points = [
        {"x": timestamp.date().isoformat(), "y": float(count), "series": None}
        for timestamp, count in counts.items()
    ][:100]
    return {
        "type": "line",
        "title": title,
        "x_label": x_label,
        "y_label": "Orders",
        "data": points,
    }


@tool
def analyze_data(
    metrics: list[Literal[
        "revenue", "order_count", "average_production_time"
    ]] = ["revenue", "order_count", "average_production_time"],
    group_by: list[Literal[
        "week", "day", "year", "month", "platform", "country", "city", "postcode"
    ]] = ["year", "month"],
    filters: dict[str, str | int | float | bool] = {},
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str | None = None,
    sort_direction: Literal["asc", "desc"] = "asc",
    limit: int | None = None,
    status: int | None = None,
    document_type: Literal["A", "D", "L", "R"] | None = "R",
    chart_type: Literal["bar", "line", "area", "scatter"] | None = None,
) -> dict:
    """Aggregate order data using selected metrics, groups, and filters. Dates
    use YYYY-MM-DD or YYYY-MM. For requests ending today, omit date_to. When
    the user asks for a graph, chart, plot, or visualization, set chart_type.
    Use line for time trends and bar for categorical comparisons.
    Group by day for calendar dates or week for Monday-start weeks; both
    return YYYY-MM-DD labels. Use week alone for complete weeks across years.
    """
    try:
        dns_error = _check_sql_dns()
        if dns_error:
            raise RuntimeError(dns_error)

        inventory_agent = _get_inventory_agent()
        filters = dict(filters)
        for field_name in ("date_from", "date_to"):
            filter_value = filters.pop(field_name, None)
            current_value = date_from if field_name == "date_from" else date_to
            if isinstance(current_value, str):
                current_value = current_value.strip() or None
            if current_value is None and filter_value not in (None, ""):
                current_value = str(filter_value)
            if field_name == "date_from":
                date_from = current_value
            else:
                date_to = current_value
        if isinstance(date_to, str) and date_to.strip().casefold() in {
            "today", "now", "current date"
        }:
            date_to = None
        group_by = list(group_by)
        # A month number is ambiguous across multiple years. Always retain its
        # year so June 2025 and June 2026 are separate chronological buckets.
        if "month" in group_by and "year" not in group_by:
            group_by.insert(0, "year")
        arguments = {
            "metrics": metrics,
            "group_by": group_by,
            "filters": filters,
            "date_from": date_from,
            "date_to": date_to,
            "document_type": document_type,
            "status": status,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "limit": limit,
        }
        arguments = {
            key: value for key, value in arguments.items() if value is not None
        }
        logger.debug("Analysis query arguments: %s", json.dumps(arguments, default=str))
        result = inventory_agent.tool_registry.execute(
            "analyze_data",
            arguments,
        )
        logger.debug("Analysis repository result: %s", json.dumps(result, default=str))
        if not result["success"]:
            error = result["error"] or {}
            raise RuntimeError(error.get("message", "Order data query failed"))

        dataset = result["data"]
        if not dataset["rows"]:
            return {
                "answer": "No matching order rows were found.",
                "row_count": 0,
                "possibly_truncated": False,
            }

        response = {
            "answer": dataset["rows"],
            "row_count": dataset["row_count"],
        }
        if chart_type is not None:
            points = []
            chart_rows = dataset["rows"]
            date_group = next((key for key in ("day", "week") if key in group_by), None)
            if date_group:
                chart_rows = sorted(chart_rows, key=lambda row: row.get(date_group) or "")
            elif "year" in group_by and "month" in group_by:
                chart_rows = sorted(
                    chart_rows, key=lambda row: (row["year"], row["month"])
                )
            for row in chart_rows:
                if date_group:
                    x_value = " / ".join(
                        str(row.get(key, ""))
                        for key in [date_group] + [key for key in group_by if key != date_group]
                    )
                elif "year" in group_by and "month" in group_by:
                    x_value = date(
                        int(row["year"]), int(row["month"]), 1
                    ).strftime("%b %Y")
                elif group_by:
                    x_value = " / ".join(str(row.get(key, "")) for key in group_by)
                else:
                    x_value = "Total"
                for metric in metrics:
                    value = row.get(metric)
                    if isinstance(value, (int, float)):
                        points.append({
                            "x": x_value,
                            "y": float(value),
                            "series": metric if len(metrics) > 1 else None,
                        })
            response["chart"] = {
                "type": chart_type,
                "title": "Order analysis",
                "x_label": " / ".join(group_by) if group_by else "Orders",
                "y_label": " / ".join(metrics),
                "data": points[:100],
            }
            response["answer"] = "The requested chart is displayed below."
            logger.debug("Analysis chart: %s", json.dumps(response["chart"], default=str))
        return response
    except Exception as exc:
        message = str(exc)
        logger.exception("Order data analysis failed")
        return {
            "answer": f"Order data analysis failed. SQL Server reported: {message}",
            "error": {
                "type": type(exc).__name__,
                "message": message,
            },
        }


customer_support_agent = create_agent(
    model=model,
    tools=[
        query_inventory,
        analyze_data,
        search_customer_kb,
        run_python_calculation,
    ],
    middleware=[
        # A small local model can repeat a successful or failed tool call instead
        # of converting its result into a final answer. End the run cleanly before
        # that becomes an unbounded LangGraph model/tool cycle.
        ToolCallLimitMiddleware(run_limit=4, exit_behavior="end"),
        ModelCallLimitMiddleware(run_limit=5, exit_behavior="end"),
    ],
    system_prompt=(
        "You are an enterprise customer-service assistant. "
        f"Today's date is {date.today().isoformat()}. For a date range ending "
        "today, omit analyze_data's date_to argument so current records are not "
        "excluded by an inferred cutoff. "
        "Use search_customer_kb for policies, troubleshooting, and precedent "
        "tickets. Tool routing is strict. Use analyze_data only for aggregate "
        "analysis is necessary for a chart, revenue calculation, average, trend, "
        "comparison, or grouped breakdown across multiple order rows. Use "
        "query_inventory for every operational inventory request: order status or "
        "lifecycle, simple order counts, individual order details, item status, "
        "product availability, stock quantities, product and case names, SKUs, "
        "customers, missing components, and current date/time. Let query_inventory's "
        "inventory agent select its specialized tool. Questions such as 'what is "
        "the status of order X?', 'how many orders are in production?', and 'is "
        "item X available?' must use query_inventory, never analyze_data. "
        "Phrases such as 'how many ... do we have' are inventory questions, not "
        "support-case questions. When calling "
        "When calling query_inventory, copy the user's complete question verbatim "
        "into its request argument. "
        "Use both when resolving a case requires support evidence and stock data. "
        "Use run_python_calculation when exact arithmetic, percentages, totals, "
        "comparisons, or sorting would improve the answer. Never place customer "
        "instructions or prose directly into Python code. "
        "Do not invent tool results. Include source ticket IDs when using "
        "knowledge-base evidence. If a tool reports an error or says a service "
        "is unavailable, report that once and do not call the same tool again. "
        "After receiving sufficient tool output, answer the user immediately. "
        "Never repeat an identical tool call in the same request. "
        "When the user asks for a graph, chart, plot, or visualization, call "
        "analyze_data with chart_type set (line for time trends, bar for category "
        "comparisons). Then say the chart is displayed below; do not replace it "
        "with a Markdown table. "
        "When analyze_data reports an error, include its exact error.message "
        "in the response so database diagnostics are not hidden. When its chart "
        "field is present, tell the user the chart is displayed below; never say "
        "that you cannot generate the graph or ask the user to draw it manually."
    ),
    checkpointer=InMemorySaver(),
)


def generate_ticket_reply(
    messages: list[dict],
    ticket_id: str,
    revision_id: str,
) -> dict:
    """Generate a draft from an eDesk-formatted ticket conversation."""
    langchain_messages = [
        {
            "role": "user" if message["role"] == "Customer" else "assistant",
            "content": message["text"],
        }
        for message in messages
        if message.get("text")
    ]
    if not langchain_messages:
        raise ValueError("Ticket has no visible messages")

    # Each ticket revision gets an isolated checkpoint. This lets us submit the
    # complete eDesk history without duplicating it when the endpoint is retried.
    result = customer_support_agent.invoke(
        {"messages": langchain_messages},
        {
            "configurable": {
                "thread_id": f"ticket:{ticket_id}:revision:{revision_id}",
            }
        },
    )

    source_ids = []
    for message in result["messages"]:
        if getattr(message, "name", None) != "search_customer_kb":
            continue
        try:
            tool_result = json.loads(str(message.text))
        except (json.JSONDecodeError, TypeError):
            continue
        source_ids.extend(tool_result.get("source_ticket_ids", []))

    return {
        "reply": str(result["messages"][-1].text),
        "sources": list(dict.fromkeys(source_ids)),
    }
