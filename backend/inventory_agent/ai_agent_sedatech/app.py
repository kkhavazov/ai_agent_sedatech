from __future__ import annotations

from factory import build_agent


def main() -> None:
    agent = build_agent()
    print("Sedatech support agent. Type 'exit' to stop.\n")

    while True:
        try:
            request = input("Request: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopped.")
            break

        if request.lower() in {"exit", "quit"}:
            break
        if not request:
            continue

        try:
            result = agent.handle_request(request)
        except Exception as exc:
            print(f"\nError: {exc}\n")
            continue

        print(f"\nModel: {result.model_name}")
        print("\nDraft:\n")
        print(result.draft)

        if result.tool_calls:
            print(f"\nTool calls: {len(result.tool_calls)}")
        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"- {warning}")
        print()


if __name__ == "__main__":
    main()
