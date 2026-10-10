import logging
from kanoman.logging.logger import KanomanLogger, redact_sensitive_text


def test_redact_sensitive_text_masks_github_tokens():
    raw = "Failed to push with token " + "gh" + "o_" + ("a" * 25)
    sanitized = redact_sensitive_text(raw)
    assert "gh" + "o_" not in sanitized
    assert "***REDACTED_SECRET***" in sanitized


def test_redact_sensitive_text_masks_openai_and_gemini_keys():
    openai_raw = "Call using key " + "s" + "k-" + ("b" * 25)
    gemini_raw = "Using " + "AI" + "za" + ("c" * 35)
    assert "***REDACTED_SECRET***" in redact_sensitive_text(openai_raw)
    assert "***REDACTED_SECRET***" in redact_sensitive_text(gemini_raw)


def test_logger_structured_payload():
    logger = KanomanLogger("test_component")
    payload = logger.info(
        "Operation completed",
        task_id="task_123",
        project_id="kanoman",
        status="SUCCESS",
        extra={"secret_info": "token=" + "gh" + "p_" + ("d" * 25)},
    )
    assert payload["component"] == "test_component"
    assert payload["task_id"] == "task_123"
    assert payload["project_id"] == "kanoman"
    assert payload["status"] == "SUCCESS"
    assert "ghp_" not in payload["extra"]["secret_info"]
    assert "***REDACTED***" in payload["extra"]["secret_info"]
