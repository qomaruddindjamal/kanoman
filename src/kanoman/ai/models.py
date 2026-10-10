"""Domain models and exceptions for AI Provider integrations."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIErrorType(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    INVALID_RESPONSE_ERROR = "INVALID_RESPONSE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class AIException(Exception):
    """Normalized exception raised by AI provider adapters."""

    def __init__(
        self,
        error_type: AIErrorType,
        message: str,
        provider: str,
        status_code: Optional[int] = None,
    ) -> None:
        self.error_type = error_type
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {error_type.value}: {message}")


class AIMessage(BaseModel):
    """Normalized chat message structure."""

    role: str = Field(..., description="Role of author: system, user, assistant.")
    content: str = Field(..., description="Content of the message.")


class UsageMetadata(BaseModel):
    """Token usage metrics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AIResponse(BaseModel):
    """Normalized response payload from an AI provider."""

    provider: str
    model_name: str
    content: str
    usage: UsageMetadata = Field(default_factory=UsageMetadata)
    structured_data: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None


class AIProviderCapabilities(BaseModel):
    """Feature capabilities exposed by a provider."""

    supports_streaming: bool = False
    supports_structured_output: bool = True
    supports_vision: bool = False
    max_context_tokens: int = 32768
