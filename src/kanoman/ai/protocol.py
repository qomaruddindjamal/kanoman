"""Abstract interface definition for AI providers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from kanoman.ai.models import AIMessage, AIProviderCapabilities, AIResponse


@runtime_checkable
class BaseAIProvider(Protocol):
    """Protocol defining mandatory behavior for AI providers."""

    @property
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'mock', 'gemini', 'ollama')."""
        ...

    def get_capabilities(self) -> AIProviderCapabilities:
        """Return provider capabilities."""
        ...

    def health_check(self) -> bool:
        """Check availability and connectivity of provider."""
        ...

    def generate_text(
        self,
        messages: List[AIMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """Generate textual completion from a list of normalized messages."""
        ...

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        """Generate JSON structured output conforming to schema."""
        ...
