"""Google Gemini API Provider Adapter."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from pydantic import SecretStr
from kanoman.ai.models import (
    AIErrorType,
    AIException,
    AIMessage,
    AIProviderCapabilities,
    AIResponse,
    UsageMetadata,
)
from kanoman.logging.logger import get_logger

logger = get_logger("ai.gemini")


class GeminiAIProvider:
    """Adapter for Google Gemini API."""

    def __init__(
        self,
        api_key: Optional[SecretStr] = None,
        model_name: str = "gemini-2.5-flash",
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def provider_name(self) -> str:
        return "gemini"

    def get_capabilities(self) -> AIProviderCapabilities:
        return AIProviderCapabilities(
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=True,
            max_context_tokens=1048576,
        )

    def health_check(self) -> bool:
        """Verify API key configuration."""
        if not self.api_key:
            return False
        return True

    def _convert_messages(self, messages: List[AIMessage]) -> List[Dict[str, Any]]:
        contents = []
        for msg in messages:
            role = "user" if msg.role in {"user", "system"} else "model"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return contents

    def generate_text(
        self,
        messages: List[AIMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        if not self.api_key or not self.api_key.get_secret_value():
            raise AIException(
                error_type=AIErrorType.AUTHENTICATION_ERROR,
                message="Gemini API Key is missing or not configured.",
                provider=self.provider_name,
            )

        if not messages:
            raise AIException(
                error_type=AIErrorType.VALIDATION_ERROR,
                message="Cannot generate text with empty message list.",
                provider=self.provider_name,
            )

        key_val = self.api_key.get_secret_value()
        endpoint = f"{self.base_url}/models/{self.model_name}:generateContent?key={key_val}"

        req_body: Dict[str, Any] = {
            "contents": self._convert_messages(messages),
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens:
            req_body["generationConfig"]["maxOutputTokens"] = max_tokens

        data = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start_t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                latency = (time.time() - start_t) * 1000.0
                resp_json = json.loads(body)

                text = ""
                candidates = resp_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")

                usage_dict = resp_json.get("usageMetadata", {})
                usage = UsageMetadata(
                    prompt_tokens=usage_dict.get("promptTokenCount", 0),
                    completion_tokens=usage_dict.get("candidatesTokenCount", 0),
                    total_tokens=usage_dict.get("totalTokenCount", 0),
                )

                return AIResponse(
                    provider=self.provider_name,
                    model_name=self.model_name,
                    content=text,
                    usage=usage,
                    latency_ms=latency,
                )
        except urllib.error.HTTPError as he:
            err_msg = f"HTTP Error {he.code}"
            if he.code in {401, 403}:
                err_type = AIErrorType.AUTHENTICATION_ERROR
            elif he.code == 429:
                err_type = AIErrorType.RATE_LIMIT_ERROR
            elif he.code >= 500:
                err_type = AIErrorType.SERVICE_UNAVAILABLE
            else:
                err_type = AIErrorType.INVALID_RESPONSE_ERROR
            raise AIException(
                error_type=err_type,
                message=err_msg,
                provider=self.provider_name,
                status_code=he.code,
            ) from he
        except urllib.error.URLError as ue:
            raise AIException(
                error_type=AIErrorType.TIMEOUT_ERROR,
                message=f"Network error: {str(ue)}",
                provider=self.provider_name,
            ) from ue

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        # Prompting for JSON output conforming to schema
        system_instruction = f"\nYou must output strictly valid JSON adhering to this schema: {json.dumps(schema)}"
        augmented_messages = messages.copy()
        if augmented_messages:
            augmented_messages[-1] = AIMessage(
                role=augmented_messages[-1].role,
                content=augmented_messages[-1].content + system_instruction,
            )

        resp = self.generate_text(augmented_messages, temperature=temperature)
        try:
            parsed = json.loads(resp.content)
            resp.structured_data = parsed
        except json.JSONDecodeError:
            resp.structured_data = None
        return resp
