"""Optional local model adapter for Ollama."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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

logger = get_logger("ai.ollama")


class OllamaAIProvider:
    """Adapter for self-hosted local models via Ollama."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model_name: str = "llama3:latest",
        timeout: int = 60,
    ) -> None:
        self.host = host.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "ollama"

    def get_capabilities(self) -> AIProviderCapabilities:
        return AIProviderCapabilities(
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=False,
            max_context_tokens=8192,
        )

    def health_check(self) -> bool:
        """Check if local Ollama server is responding."""
        endpoint = f"{self.host}/api/version"
        req = urllib.request.Request(endpoint, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate_text(
        self,
        messages: List[AIMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        endpoint = f"{self.host}/api/chat"
        formatted_msgs = [{"role": m.role, "content": m.content} for m in messages]
        payload = {
            "model": self.model_name,
            "messages": formatted_msgs,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                res_body = json.loads(resp.read().decode("utf-8"))
                text = res_body.get("message", {}).get("content", "")
                eval_count = res_body.get("eval_count", 0)
                prompt_eval = res_body.get("prompt_eval_count", 0)

                return AIResponse(
                    provider=self.provider_name,
                    model_name=self.model_name,
                    content=text,
                    usage=UsageMetadata(
                        prompt_tokens=prompt_eval,
                        completion_tokens=eval_count,
                        total_tokens=prompt_eval + eval_count,
                    ),
                )
        except urllib.error.URLError as ue:
            raise AIException(
                error_type=AIErrorType.SERVICE_UNAVAILABLE,
                message=f"Local Ollama daemon unreachable at {self.host}: {str(ue)}",
                provider=self.provider_name,
            ) from ue

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        system_instruction = f"\nReturn strictly valid JSON conforming to: {json.dumps(schema)}"
        augmented = messages.copy()
        if augmented:
            augmented[-1] = AIMessage(
                role=augmented[-1].role,
                content=augmented[-1].content + system_instruction,
            )
        resp = self.generate_text(augmented, temperature=temperature)
        try:
            resp.structured_data = json.loads(resp.content)
        except json.JSONDecodeError:
            resp.structured_data = None
        return resp
