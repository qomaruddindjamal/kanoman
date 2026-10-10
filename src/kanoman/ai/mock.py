"""Mock AI Provider for deterministic offline testing and CI workflows."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from kanoman.ai.models import (
    AIErrorType,
    AIException,
    AIMessage,
    AIProviderCapabilities,
    AIResponse,
    UsageMetadata,
)
from kanoman.logging.logger import get_logger

logger = get_logger("ai.mock")


class MockAIProvider:
    """Mock implementation of BaseAIProvider."""

    def __init__(
        self,
        name: str = "mock",
        default_reply: str = "Mock AI response: analysis completed successfully.",
        simulate_error: Optional[AIErrorType] = None,
        simulate_latency_ms: float = 0.0,
    ) -> None:
        self._name = name
        self._default_reply = default_reply
        self._simulate_error = simulate_error
        self._simulate_latency_ms = simulate_latency_ms
        self.call_count = 0
        self.last_messages: List[AIMessage] = []

    @property
    def provider_name(self) -> str:
        return self._name

    def get_capabilities(self) -> AIProviderCapabilities:
        return AIProviderCapabilities(
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=False,
            max_context_tokens=8192,
        )

    def health_check(self) -> bool:
        if self._simulate_error == AIErrorType.SERVICE_UNAVAILABLE:
            return False
        return True

    def _maybe_raise(self) -> None:
        if self._simulate_error:
            raise AIException(
                error_type=self._simulate_error,
                message=f"Simulated error: {self._simulate_error.value}",
                provider=self.provider_name,
            )

    def generate_text(
        self,
        messages: List[AIMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        self.call_count += 1
        self.last_messages = messages
        if self._simulate_latency_ms > 0:
            time.sleep(self._simulate_latency_ms / 1000.0)

        self._maybe_raise()

        if not messages:
            raise AIException(
                error_type=AIErrorType.VALIDATION_ERROR,
                message="Cannot generate text with empty message list.",
                provider=self.provider_name,
            )

        prompt_len = sum(len(m.content) for m in messages)
        return AIResponse(
            provider=self.provider_name,
            model_name="mock-model-v1",
            content=self._default_reply,
            usage=UsageMetadata(
                prompt_tokens=prompt_len // 4,
                completion_tokens=len(self._default_reply) // 4,
                total_tokens=(prompt_len + len(self._default_reply)) // 4,
            ),
            latency_ms=self._simulate_latency_ms,
        )

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        self.call_count += 1
        self.last_messages = messages
        self._maybe_raise()

        # Generate sample conforming structure
        structured_mock: Dict[str, Any] = {
            "status": "success",
            "summary": "Mock structured result",
            "confidence": 0.99,
        }
        return AIResponse(
            provider=self.provider_name,
            model_name="mock-model-v1",
            content=json.dumps(structured_mock),
            structured_data=structured_mock,
            usage=UsageMetadata(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )
