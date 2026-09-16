from __future__ import annotations

from agent.orchestrator import SupportAgent
from config import Settings
from llm.gemini_client import GeminiClient
from llm.model_router import ModelRouter
from llm.ollama_client import OllamaClient
from repositories.demo_order_repository import DemoOrderRepository
from repositories.demo_item_repository import DemoItemRepository
from repositories.item_repository import ItemRepository
from repositories.order_repository import OrderRepository
from repositories.sqlserver_item_repository import SqlServerItemRepository
from repositories.sqlserver_emails_repository import SqlServerEmailsRepository
from repositories.sqlserver_missing_repository import SqlServerMissingRepository
from repositories.sqlserver_order_repository import SqlServerOrderRepository
from services.item_service import ItemService
from services.missing_service import MissingComponentService
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


def build_item_repository(settings: Settings) -> ItemRepository:
    if settings.repository_backend == "sqlserver":
        return SqlServerItemRepository(
            server=settings.sqlserver_server,
            user=settings.sqlserver_user,
            password=settings.sqlserver_password,
            database=settings.sqlserver_database,
            tds_version=settings.sqlserver_tds_version,
            port=settings.sqlserver_port,
            login_timeout_seconds=settings.sqlserver_login_timeout_seconds,
            query_timeout_seconds=settings.sqlserver_query_timeout_seconds,
        )
    return DemoItemRepository()


def build_agent(settings: Settings | None = None) -> SupportAgent:
    settings = settings or Settings()
    settings.validate()

    repository = build_repository(settings)
    order_service = OrderService(repository)
    item_service = ItemService(build_item_repository(settings))
    missing_component_service = None
    emails_repository = None
    if settings.repository_backend == "sqlserver":
        emails_repository = SqlServerEmailsRepository(
            server=settings.sqlserver_server,
            user=settings.sqlserver_user,
            password=settings.sqlserver_password,
            database=settings.sqlserver_database,
            tds_version=settings.sqlserver_tds_version,
            port=settings.sqlserver_port,
            login_timeout_seconds=settings.sqlserver_login_timeout_seconds,
            query_timeout_seconds=settings.sqlserver_query_timeout_seconds,
        )
        missing_repository = SqlServerMissingRepository(
            server=settings.sqlserver_server or "",
            user=settings.sqlserver_user or "",
            password=settings.sqlserver_password or "",
            database=settings.sqlserver_database or "",
            tds_version=settings.sqlserver_tds_version,
            port=settings.sqlserver_port,
            login_timeout_seconds=(
                settings.sqlserver_login_timeout_seconds
            ),
            query_timeout_seconds=(
                settings.sqlserver_query_timeout_seconds
            ),
        )
        missing_component_service = MissingComponentService(
            missing_repository
        )
    tool_registry = build_tool_registry(
        order_service,
        item_service,
        missing_component_service,
        emails_repository=emails_repository,
    )


    local_client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        settings=settings,
    )

    gemini_client = None
    if settings.gemini_api_key:
        gemini_client = GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    router = ModelRouter(
        local_client=local_client,
        gemini_client=gemini_client,
        provider=settings.model_provider,
    )

    return SupportAgent(model_router=router, tool_registry=tool_registry)
