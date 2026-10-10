import pytest
from kanoman.ai.models import (
    AIErrorType,
    AIException,
    AIMessage,
    AIProviderCapabilities,
)
from kanoman.ai.protocol import BaseAIProvider
from kanoman.ai.mock import MockAIProvider
from kanoman.ai.gemini import GeminiAIProvider
from kanoman.ai.ollama import OllamaAIProvider
from kanoman.ai.router import AIRouter


def test_mock_provider_implements_protocol():
    mock = MockAIProvider()
    assert isinstance(mock, BaseAIProvider)
    assert mock.provider_name == "mock"
    assert mock.health_check() is True


def test_mock_provider_generates_text_and_counts_usage():
    mock = MockAIProvider(default_reply="Synthesized response.")
    msgs = [AIMessage(role="user", content="Explain hexagonal architecture.")]
    res = mock.generate_text(msgs)

    assert res.provider == "mock"
    assert res.content == "Synthesized response."
    assert res.usage.total_tokens > 0
    assert mock.call_count == 1


def test_mock_provider_generates_structured():
    mock = MockAIProvider()
    msgs = [AIMessage(role="user", content="Give me structured status.")]
    res = mock.generate_structured(msgs, schema={"type": "object"})

    assert res.structured_data is not None
    assert res.structured_data["status"] == "success"


def test_mock_provider_simulates_rate_limit_error():
    mock = MockAIProvider(simulate_error=AIErrorType.RATE_LIMIT_ERROR)
    msgs = [AIMessage(role="user", content="Ping")]

    with pytest.raises(AIException) as excinfo:
        mock.generate_text(msgs)
    assert excinfo.value.error_type == AIErrorType.RATE_LIMIT_ERROR


def test_provider_rejects_empty_messages():
    mock = MockAIProvider()
    with pytest.raises(AIException) as excinfo:
        mock.generate_text([])
    assert excinfo.value.error_type == AIErrorType.VALIDATION_ERROR


def test_gemini_provider_fails_safely_without_key():
    gemini = GeminiAIProvider(api_key=None)
    msgs = [AIMessage(role="user", content="Hello Gemini")]
    with pytest.raises(AIException) as excinfo:
        gemini.generate_text(msgs)
    assert excinfo.value.error_type == AIErrorType.AUTHENTICATION_ERROR


def test_ollama_provider_health_check_false_when_unreachable():
    ollama = OllamaAIProvider(host="http://localhost:59999")
    assert ollama.health_check() is False


def test_ai_router_routes_to_mock_and_handles_fallback():
    failing_mock = MockAIProvider(name="flaky", simulate_error=AIErrorType.RATE_LIMIT_ERROR)
    # Create healthy mock
    healthy_mock = MockAIProvider(name="mock", default_reply="Fallback rescued request.")

    router = AIRouter()
    router.register_provider(failing_mock)
    router.register_provider(healthy_mock)

    msgs = [AIMessage(role="user", content="Execute with fallback")]
    res = router.generate_text(msgs, primary_name="flaky", fallback_name="mock")

    assert res.content == "Fallback rescued request."
    assert res.provider == "mock"
