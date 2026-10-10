"""Structured, sanitized logging system for Kanoman AI.

Guarantees:
- Structured output (timestamp, level, component, task_id, project_id, status, message).
- Automatic redaction of sensitive credentials (API keys, GitHub tokens, passwords).
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Regex patterns for sensitive tokens
REDACTION_PATTERNS = [
    re.compile(r"gho_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE),
    re.compile(r"(password|token|secret|api_key|apikey)=([^\s&]+)", re.IGNORECASE),
]


def redact_sensitive_text(text: str) -> str:
    """Mask known secret patterns from strings."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern in REDACTION_PATTERNS:
        if "=" in pattern.pattern:
            sanitized = pattern.sub(r"\1=***REDACTED***", sanitized)
        else:
            sanitized = pattern.sub("***REDACTED_SECRET***", sanitized)
    return sanitized


class SanitizingFormatter(logging.Formatter):
    """Logging formatter that automatically sanitizes all messages."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_sensitive_text(original)


class KanomanLogger:
    """Structured logger providing task-aware, sanitized telemetry."""

    def __init__(self, component: str = "core", level: int = logging.INFO):
        self.component = component
        self._logger = logging.getLogger(f"kanoman.{component}")
        self._logger.setLevel(level)

        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = SanitizingFormatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def log(
        self,
        level: int,
        message: str,
        *,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Emit a structured, sanitized log event."""
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": logging.getLevelName(level),
            "component": self.component,
            "message": redact_sensitive_text(message),
        }
        if task_id:
            payload["task_id"] = task_id
        if project_id:
            payload["project_id"] = project_id
        if status:
            payload["status"] = status
        if extra:
            sanitized_extra = {}
            for k, v in extra.items():
                if isinstance(v, str):
                    sanitized_extra[k] = redact_sensitive_text(v)
                else:
                    sanitized_extra[k] = v
            payload["extra"] = sanitized_extra

        # Format as compact string for standard console handler
        summary = f"[{payload.get('status', 'INFO')}] {payload['message']}"
        if task_id:
            summary = f"[Task:{task_id}] {summary}"
        self._logger.log(level, summary)
        return payload

    def info(self, message: str, **kwargs: Any) -> Dict[str, Any]:
        return self.log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> Dict[str, Any]:
        return self.log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> Dict[str, Any]:
        return self.log(logging.ERROR, message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> Dict[str, Any]:
        return self.log(logging.DEBUG, message, **kwargs)


def get_logger(component: str = "core") -> KanomanLogger:
    """Factory helper to obtain a named KanomanLogger instance."""
    return KanomanLogger(component=component)
