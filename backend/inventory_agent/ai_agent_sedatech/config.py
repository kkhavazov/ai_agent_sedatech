from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be an integer"
        ) from exc


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    model_provider: str = os.getenv("MODEL_PROVIDER", "local")
    ollama_base_url: str = os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434",
    )
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    ollama_timeout_seconds: int = _get_int(
        "OLLAMA_TIMEOUT_SECONDS",
        120,
    )

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    )

    repository_backend: str = os.getenv(
        "REPOSITORY_BACKEND",
        "demo",
    )

    sqlserver_server: str | None = (
        os.getenv("SQLSERVER_SERVER") or None
    )
    sqlserver_user: str | None = (
        os.getenv("SQLSERVER_USER") or None
    )
    sqlserver_password: str | None = (
        os.getenv("SQLSERVER_PASSWORD") or None
    )
    sqlserver_database: str | None = (
        os.getenv("SQLSERVER_DATABASE") or None
    )

    sqlserver_tds_version: str = os.getenv(
        "SQLSERVER_TDS_VERSION",
        "7.0",
    )
    sqlserver_port: str = os.getenv(
        "SQLSERVER_PORT",
        "1433",
    )
    sqlserver_login_timeout_seconds: int = _get_int(
        "SQLSERVER_LOGIN_TIMEOUT_SECONDS",
        10,
    )
    sqlserver_query_timeout_seconds: int = _get_int(
        "SQLSERVER_QUERY_TIMEOUT_SECONDS",
        30,
    )
    forecast_run_hour: int = _get_int("FORECAST_RUN_HOUR", 8)
    forecast_run_minute: int = _get_int("FORECAST_RUN_MINUTE", 0)
    forecast_weeks: int = _get_int("FORECAST_WEEKS", 1)

    def validate(self) -> None:
        if self.model_provider not in {
            "local",
            "gemini",
            "hybrid",
        }:
            raise ValueError(
                "MODEL_PROVIDER must be local, gemini, or hybrid"
            )

        if self.repository_backend not in {
            "demo",
            "sqlserver",
        }:
            raise ValueError(
                "REPOSITORY_BACKEND must be demo or sqlserver"
            )

        if not 0 <= self.forecast_run_hour <= 23:
            raise ValueError("FORECAST_RUN_HOUR must be between 0 and 23")
        if not 0 <= self.forecast_run_minute <= 59:
            raise ValueError("FORECAST_RUN_MINUTE must be between 0 and 59")
        if not 1 <= self.forecast_weeks <= 52:
            raise ValueError("FORECAST_WEEKS must be between 1 and 52")

        if (
            self.model_provider in {"gemini", "hybrid"}
            and not self.gemini_api_key
        ):
            raise ValueError(
                "GEMINI_API_KEY is required for Gemini or hybrid mode"
            )

        if self.repository_backend == "sqlserver":
            values = {
                "SQLSERVER_SERVER": self.sqlserver_server,
                "SQLSERVER_USER": self.sqlserver_user,
                "SQLSERVER_PASSWORD": self.sqlserver_password,
                "SQLSERVER_DATABASE": self.sqlserver_database,
            }

            missing = [
                name
                for name, value in values.items()
                if not value
            ]

            if missing:
                raise ValueError(
                    "Missing SQL Server environment variables: "
                    + ", ".join(missing)
                )
