"""Shared model settings for the backend and standalone inventory agent."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_PROJECT = Path(__file__).resolve().parent
# Explicit paths make configuration independent of the launch directory.
# Process environment > backend .env > inventory .env > repository .env.
for _path in (_PROJECT.parents[1] / ".env", _PROJECT / ".env", _PROJECT.parents[2] / ".env"):
    load_dotenv(_path, override=False)


def _env(name: str, default, cast=str):
    def read():
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return cast(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid value for {name}") from exc
    return field(default_factory=read)


def _boolean(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError("Expected true or false")


@dataclass(frozen=True, slots=True)
class ModelSettings:
    ollama_base_url: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = _env("OLLAMA_MODEL", "qwen3.6:35b")
    ollama_timeout_seconds: int = _env("OLLAMA_TIMEOUT_SECONDS", 120, int)
    ollama_num_ctx: int = _env("OLLAMA_NUM_CTX", 16384, int)
    ollama_num_predict: int = _env("OLLAMA_NUM_PREDICT", 2048, int)
    ollama_temperature: float = _env("OLLAMA_TEMPERATURE", 0.0, float)
    ollama_think: bool = _env("OLLAMA_THINK", False, _boolean)
    ollama_keep_alive: str = _env("OLLAMA_KEEP_ALIVE", "30m")
    embedding_model: str = _env("OLLAMA_EMBED_MODEL", "bge-m3")
    embedding_num_ctx: int = _env("OLLAMA_EMBED_NUM_CTX", 8192, int)
    gemini_api_key: str | None = _env("GEMINI_API_KEY", None, lambda value: value or None)
    gemini_model: str = _env("GEMINI_MODEL", "gemini-2.5-flash")

    def __post_init__(self) -> None:
        for name in ("ollama_timeout_seconds", "ollama_num_ctx", "ollama_num_predict", "embedding_num_ctx"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not math.isfinite(self.ollama_temperature) or self.ollama_temperature < 0:
            raise ValueError("OLLAMA_TEMPERATURE must be finite and non-negative")
        for name in ("ollama_model", "embedding_model", "gemini_model", "ollama_keep_alive"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not self.ollama_base_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")

    def ollama_options(self) -> dict:
        return {
            "num_ctx": self.ollama_num_ctx,
            "num_predict": self.ollama_num_predict,
            "temperature": self.ollama_temperature,
        }

    def chat_kwargs(self) -> dict:
        return {
            "model": self.ollama_model,
            "think": self.ollama_think,
            "keep_alive": self.ollama_keep_alive,
            "options": self.ollama_options(),
        }
