from __future__ import annotations

import json

from config import Settings
from factory import build_repository
from services.order_service import OrderService
from tools.factory import build_tool_registry


def main() -> None:
    settings = Settings()
    settings.validate()

    repository = build_repository(settings)

    print("Repository backend:", settings.repository_backend)
    print("Repository class:", type(repository).__name__)
    print(
        "Repository has filter_orders:",
        hasattr(repository, "filter_orders"),
    )

    service = OrderService(repository)

    print(
        "Service has filter_orders:",
        hasattr(service, "filter_orders"),
    )

    registry = build_tool_registry(service)

    print(
        "Registered tools:",
        [
            schema["function"]["name"]
            for schema in registry.schemas()
        ],
    )

    result = registry.execute(
        "filter_orders",
        {
            "customer_name": "Lungu Nicolas",
            "limit": 20,
        },
    )

    print("\nTool result:")
    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()