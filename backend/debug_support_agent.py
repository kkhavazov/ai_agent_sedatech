"""Inspect graph queries: python backend/debug_support_agent.py "Draw ..."."""

import argparse
import json
import logging
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="Question to send to the support agent")
    parser.add_argument(
        "--analysis-json",
        help="Call analyze_data directly with JSON arguments, bypassing model routing",
    )
    args = parser.parse_args()
    if bool(args.prompt) == bool(args.analysis_json):
        parser.error("Provide either a prompt or --analysis-json")

    logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")
    logging.getLogger("customer_support_agent").setLevel(logging.DEBUG)

    from customer_support_agent import analyze_data, customer_support_agent

    if args.analysis_json:
        result = analyze_data.invoke(json.loads(args.analysis_json))
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    # A new checkpoint prevents earlier questions/results from affecting this test.
    result = customer_support_agent.invoke(
        {"messages": [{"role": "user", "content": args.prompt}]},
        {"configurable": {"thread_id": f"debug:{uuid4()}"}},
    )
    for message in result["messages"]:
        print(f"\n--- {message.type}: {getattr(message, 'name', None) or ''} ---")
        calls = getattr(message, "tool_calls", None)
        if calls:
            print("Tool calls:", json.dumps(calls, indent=2, ensure_ascii=False, default=str))
        print(message.content)


if __name__ == "__main__":
    main()
