from __future__ import annotations

from llm.base import LLMClient


class ModelRouter:
    def __init__(
        self,
        local_client: LLMClient,
        gemini_client: LLMClient | None = None,
        provider: str = "local",
    ) -> None:
        self.local_client = local_client
        self.gemini_client = gemini_client
        self.provider = provider

    def select(self, request: str) -> LLMClient:
        if self.provider == "local":
            return self.local_client
        if self.provider == "gemini":
            if self.gemini_client is None:
                raise RuntimeError("Gemini client is not configured")
            return self.gemini_client

        # Initial, intentionally simple hybrid rule. Replace later with an
        # evaluated classifier rather than adding many keyword conditions.
        complex_markers = (
            "recommend",
            "configuration",
            "compatibility",
            "diagnose",
            "warranty",
            "troubleshoot",
            "compare",
        )
        is_complex = any(marker in request.lower() for marker in complex_markers)
        if is_complex and self.gemini_client is not None:
            return self.gemini_client
        return self.local_client
