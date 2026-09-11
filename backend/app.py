import json

import pandas as pd
import streamlit as st
from customer_support_agent import customer_support_agent


def render_chart(chart: dict | None) -> None:
    if not chart or not chart.get("data"):
        return

    frame = pd.DataFrame.from_records(chart["data"])
    
    # Default to the original 'x' column
    x_col = "x"
    
    # Parse months and sort chronologically
    parsed_months = pd.to_datetime(frame["x"], format="%b %Y", errors="coerce")
    if parsed_months.notna().any():
        frame["x_date"] = parsed_months
        frame = frame.sort_values("x_date")
        # Point to the datetime column so the chart honors the timeline
        x_col = "x_date"

    title = chart.get("title")
    if title:
        st.caption(title)

    options = {
        "x": x_col,  # Uses 'x_date' if parsed successfully, else falls back to 'x'
        "y": "y",
        "x_label": chart.get("x_label"),
        "y_label": chart.get("y_label"),
    }
    
    if "series" in frame.columns and frame["series"].notna().any():
        options["color"] = "series"

    chart_type = chart.get("type", "bar")
    if chart_type == "line":
        st.line_chart(frame, **options)
    elif chart_type == "area":
        st.area_chart(frame, **options)
    elif chart_type == "scatter":
        st.scatter_chart(frame, **options)
    else:
        st.bar_chart(frame, **options)

def extract_analysis_chart(result: dict, prompt: str = "") -> dict | None:
    chart_requested = any(
        word in prompt.casefold()
        for word in ("graph", "chart", "plot", "visualization", "visualisation")
    )
    if not chart_requested:
        return None

    # With a checkpointer, invoke() returns the whole conversation. Only inspect
    # tool messages emitted after the latest user message so a chart from an
    # earlier turn cannot leak into the current response.
    messages = result.get("messages", [])
    latest_user_index = max(
        (
            index for index, message in enumerate(messages)
            if getattr(message, "type", None) == "human"
            or type(message).__name__ == "HumanMessage"
        ),
        default=-1,
    )
    current_turn_messages = messages[latest_user_index + 1:]
    for message in reversed(current_turn_messages):
        if getattr(message, "name", None) != "analyze_data":
            continue
        try:
            payload = json.loads(str(message.text))
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get("chart"):
            return payload["chart"]
        # Local models occasionally omit chart_type despite an explicit graph
        # request. Build the same native Streamlit chart from aggregate rows.
        rows = payload.get("answer")
        if not chart_requested or not isinstance(rows, list) or not rows:
            continue
        metrics = [
            key for key in ("revenue", "order_count", "average_production_time")
            if any(isinstance(row.get(key), (int, float)) for row in rows)
        ]
        groups = [
            key for key in ("year", "month", "platform", "country", "city", "postcode")
            if any(key in row for row in rows)
        ]
        points = []
        if all("year" in row and "month" in row for row in rows):
            rows = sorted(rows, key=lambda row: (row["year"], row["month"]))
        for row in rows:
            if "year" in row and "month" in row:
                from datetime import date
                x_value = date(
                    int(row["year"]), int(row["month"]), 1
                ).strftime("%b %Y")
            else:
                x_value = " / ".join(str(row.get(key, "")) for key in groups) or "Total"
            for metric in metrics:
                value = row.get(metric)
                if isinstance(value, (int, float)):
                    points.append({
                        "x": x_value, "y": float(value),
                        "series": metric if len(metrics) > 1 else None,
                    })
        return {
            "type": "line" if "year" in groups or "month" in groups else "bar",
            "title": "Order analysis",
            "x_label": " / ".join(groups) or "Orders",
            "y_label": " / ".join(metrics),
            "data": points[:100],
        }
    return None

st.title("Sedatech Assistant")

# Initialize a persistent thread ID for the session if it doesn't exist
if "thread_id" not in st.session_state:
    import uuid
    st.session_state.thread_id = str(uuid.uuid4())

config = {
    "configurable": {"thread_id": st.session_state.thread_id},
    # Bound coordinator/tool loops even if a model repeatedly selects a
    # failing dependency.
    # The agent middleware terminates repeated tool/model calls first. This
    # ceiling remains a final guard and allows legitimate multi-tool requests.
    "recursion_limit": 20,
}

# Initialize message history in streamlit session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display prior messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_chart(message.get("chart"))

# Accept user input
if prompt := st.chat_input("How can I help you with your order or support ticket?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Invoke the LangChain agent
    with st.chat_message("assistant"):
        with st.spinner("Checking inventory and knowledge base..."):
            try:
                result = customer_support_agent.invoke(
                    {"messages": [{"role": "user", "content": prompt}]},
                    config,
                )
                message = result["messages"][-1]
                answer = str(message.text)
                chart = extract_analysis_chart(result, prompt)
                if chart:
                    answer = "The requested chart is displayed below."
                st.markdown(answer)
                render_chart(chart)
            except Exception as exc:
                chart = None
                answer = (
                    "The assistant could not complete this request. "
                    f"{type(exc).__name__}: {exc}"
                )
                st.error(answer)
            
    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "chart": chart}
    )
