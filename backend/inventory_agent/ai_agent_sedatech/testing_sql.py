from __future__ import annotations

from agent.orchestrator import SupportAgent
from config import Settings
from llm.gemini_client import GeminiClient
from llm.model_router import ModelRouter
from llm.ollama_client import OllamaClient
from repositories.demo_order_repository import DemoOrderRepository
from repositories.order_repository import OrderRepository
from repositories.sqlserver_order_repository import SqlServerOrderRepository
from services.order_service import OrderService
from tools.factory import build_tool_registry


def build_repository(settings: Settings) -> OrderRepository:
    if settings.repository_backend == "sqlserver":
        if not settings.sqlserver_server:
            raise ValueError("SQLSERVER_SERVER is missing")

        if not settings.sqlserver_user:
            raise ValueError("SQLSERVER_USER is missing")

        if not settings.sqlserver_password:
            raise ValueError("SQLSERVER_PASSWORD is missing")

        if not settings.sqlserver_database:
            raise ValueError("SQLSERVER_DATABASE is missing")

        return SqlServerOrderRepository(
            server=settings.sqlserver_server,
            user=settings.sqlserver_user,
            password=settings.sqlserver_password,
            database=settings.sqlserver_database,
            tds_version=settings.sqlserver_tds_version,
            port=settings.sqlserver_port,
            login_timeout_seconds=(
                settings.sqlserver_login_timeout_seconds
            ),
            query_timeout_seconds=(
                settings.sqlserver_query_timeout_seconds
            ),
        )

    return DemoOrderRepository()

sql = build_repository(None)

result = sql.find_by_order_number(order_number = "LS163908")

print(result)