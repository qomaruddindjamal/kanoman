"""AI Provider Router with configurable fallback and token accounting."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from kanoman.ai.models import (
    AIErrorType,
    AIException,
    AIMessage,
    AIResponse,
)
from kanoman.ai.protocol import BaseAIProvider
from kanoman.config.settings import KanomanConfig, get_config
from kanoman.logging.logger import get_logger

logger = get_logger("ai.router")


class AIRouter:
    """Routes requests to primary provider with optional configured fallback."""

    def __init__(
        self,
        providers: Optional[Dict[str, BaseAIProvider]] = None,
        config: Optional[KanomanConfig] = None,
    ) -> None:
        self.config = config or get_config()
        self._providers: Dict[str, BaseAIProvider] = providers or {}

    def register_provider(self, provider: BaseAIProvider) -> None:
        """Register a provider instance."""
        self._providers[provider.provider_name.lower()] = provider

    def get_provider(self, name: str) -> Optional[BaseAIProvider]:
        """Fetch provider by name."""
        return self._providers.get(name.lower())

    def generate_text(
        self,
        messages: List[AIMessage],
        primary_name: Optional[str] = None,
        fallback_name: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """Route text generation with safe fallback logic."""
        target_name = (primary_name or self.config.default_ai_provider).lower()
        provider = self.get_provider(target_name)

        if not provider:
            raise AIException(
                error_type=AIErrorType.VALIDATION_ERROR,
                message=f"Configured primary provider '{target_name}' is not registered.",
                provider="router",
            )

        logger.info(f"Routing request to provider: {target_name}", status="AI_REQUEST")
        try:
            return provider.generate_text(messages, temperature=temperature, max_tokens=max_tokens)
        except AIException as exc:
            logger.warning(
                f"Primary provider '{target_name}' failed with {exc.error_type.value}: {str(exc)}",
                status="AI_PRIMARY_FAILED",
            )
            # Only trigger fallback for transient or availability issues
            fallback_eligible = {
                AIErrorType.RATE_LIMIT_ERROR,
                AIErrorType.TIMEOUT_ERROR,
                AIErrorType.SERVICE_UNAVAILABLE,
            }
            if exc.error_type in fallback_eligible and fallback_name and fallback_name.lower() in self._providers:
                fb_name = fallback_name.lower()
                logger.info(f"Initiating fallback to provider: {fb_name}", status="AI_FALLBACK")
                fb_provider = self._providers[fb_name]
                return fb_provider.generate_text(messages, temperature=temperature, max_tokens=max_tokens)
            raise

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        primary_name: Optional[str] = None,
        fallback_name: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AIResponse:
        """Route structured generation with safe fallback logic."""
        target_name = (primary_name or self.config.default_ai_provider).lower()
        provider = self.get_provider(target_name)

        if not provider:
            raise AIException(
                error_type=AIErrorType.VALIDATION_ERROR,
                message=f"Configured primary provider '{target_name}' is not registered.",
                provider="router",
            )

        logger.info(f"Routing structured request to provider: {target_name}", status="AI_STRUCTURED_REQUEST")
        try:
            return provider.generate_structured(messages, schema=schema, temperature=temperature)
        except AIException as exc:
            logger.warning(
                f"Primary provider '{target_name}' failed with {exc.error_type.value}: {str(exc)}",
                status="AI_PRIMARY_FAILED",
            )
            fallback_eligible = {
                AIErrorType.RATE_LIMIT_ERROR,
                AIErrorType.TIMEOUT_ERROR,
                AIErrorType.SERVICE_UNAVAILABLE,
            }
            if exc.error_type in fallback_eligible and fallback_name and fallback_name.lower() in self._providers:
                fb_name = fallback_name.lower()
                logger.info(f"Initiating fallback to provider: {fb_name}", status="AI_FALLBACK")
                fb_provider = self._providers[fb_name]
                return fb_provider.generate_structured(messages, schema=schema, temperature=temperature)
            raise
