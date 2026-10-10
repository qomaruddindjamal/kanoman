"""Configuration Engine for Kanoman AI.

Enforces:
- Strong typing and bounds via Pydantic v2.
- Safe defaults (dry-run enabled by default for Git).
- Secrets handled exclusively through SecretStr to prevent leakage in dumps/logs.
- Environment variable reading and optional .env parsing without external dependencies.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class EnvironmentType(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"
    CI = "ci"


class KanomanConfig(BaseModel):
    """Central validated configuration model for Kanoman AI."""

    env: EnvironmentType = Field(
        default=EnvironmentType.DEVELOPMENT,
        description="Active runtime environment.",
    )
    workspace_root: Path = Field(
        default=Path("C:/kanoman"),
        description="Root workspace directory for Kanoman operations.",
    )
    checkpoint_dir: Path = Field(
        default=Path("C:/kanoman/.kanoman_checkpoints"),
        description="Directory where atomic checkpoint snapshots are persisted.",
    )

    # Git Policies
    git_dry_run: bool = Field(
        default=True,
        description="Enforces dry-run mode for all automated Git mutation operations.",
    )
    git_allowed_remote: str = Field(
        default="https://github.com/qomaruddindjamal/kanoman.git",
        description="Target remote Git URL permitted for operations.",
    )
    git_allowed_branches: List[str] = Field(
        default_factory=lambda: ["main", "develop"],
        description="List of branches permitted for commit/push operations.",
    )

    # AI Provider Settings
    default_ai_provider: str = Field(
        default="mock",
        description="Default AI provider adapter (mock, gemini, ollama).",
    )
    ai_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Subprocess or HTTP call timeout for AI providers in seconds.",
    )
    ai_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry count for transient AI provider failures.",
    )

    # Secrets (Always protected via SecretStr)
    gemini_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Google Gemini API key (optional).",
    )
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="Local Ollama endpoint URL.",
    )

    @field_validator("workspace_root", "checkpoint_dir", mode="before")
    @classmethod
    def normalize_paths(cls, v: Any) -> Path:
        if isinstance(v, (str, Path)):
            return Path(v).resolve()
        raise ValueError(f"Invalid path specification: {v}")

    @field_validator("git_allowed_remote")
    @classmethod
    def validate_remote_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("git@")):
            raise ValueError(f"Remote URL must start with https:// or git@, got: {v}")
        return v

    @field_validator("default_ai_provider")
    @classmethod
    def validate_provider_name(cls, v: str) -> str:
        allowed = {"mock", "gemini", "ollama"}
        clean = v.strip().lower()
        if clean not in allowed:
            raise ValueError(f"Unsupported AI provider: {clean}. Allowed: {allowed}")
        return clean

    @model_validator(mode="after")
    def validate_security_invariants(self) -> KanomanConfig:
        # In CI environment, dry_run MUST be enabled unless explicitly overridden with valid auth
        if self.env == EnvironmentType.CI and not self.git_dry_run:
            if not os.environ.get("KANOMAN_CI_ALLOW_MUTATING_GIT"):
                self.git_dry_run = True
        return self

    def model_dump_safe(self) -> Dict[str, Any]:
        """Dump configuration dictionary with all secrets masked."""
        data = self.model_dump()
        for k, v in data.items():
            if isinstance(v, Path):
                data[k] = str(v)
            elif isinstance(v, SecretStr):
                data[k] = "***REDACTED***"
        if self.gemini_api_key:
            data["gemini_api_key"] = "***REDACTED***"
        return data

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> KanomanConfig:
        """Construct configuration by inspecting environment variables and optional .env."""
        # Read .env file if present
        target_env = env_file or Path(".env")
        env_vars: Dict[str, str] = {}
        if target_env.is_file():
            try:
                for line in target_env.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip("'\"")
            except Exception:
                pass

        # Merge with os.environ taking precedence
        merged = {**env_vars, **os.environ}

        kwargs: Dict[str, Any] = {}
        if "KANOMAN_ENV" in merged:
            kwargs["env"] = merged["KANOMAN_ENV"].lower()
        if "KANOMAN_WORKSPACE_ROOT" in merged:
            kwargs["workspace_root"] = Path(merged["KANOMAN_WORKSPACE_ROOT"])
        if "KANOMAN_CHECKPOINT_DIR" in merged:
            kwargs["checkpoint_dir"] = Path(merged["KANOMAN_CHECKPOINT_DIR"])
        if "KANOMAN_GIT_DRY_RUN" in merged:
            kwargs["git_dry_run"] = merged["KANOMAN_GIT_DRY_RUN"].lower() in {"true", "1", "yes"}
        if "KANOMAN_GIT_ALLOWED_REMOTE" in merged:
            kwargs["git_allowed_remote"] = merged["KANOMAN_GIT_ALLOWED_REMOTE"]
        if "KANOMAN_GIT_ALLOWED_BRANCHES" in merged:
            kwargs["git_allowed_branches"] = [
                b.strip() for b in merged["KANOMAN_GIT_ALLOWED_BRANCHES"].split(",") if b.strip()
            ]
        if "KANOMAN_DEFAULT_AI_PROVIDER" in merged:
            kwargs["default_ai_provider"] = merged["KANOMAN_DEFAULT_AI_PROVIDER"]
        if "KANOMAN_AI_TIMEOUT_SECONDS" in merged:
            kwargs["ai_timeout_seconds"] = int(merged["KANOMAN_AI_TIMEOUT_SECONDS"])
        if "KANOMAN_AI_MAX_RETRIES" in merged:
            kwargs["ai_max_retries"] = int(merged["KANOMAN_AI_MAX_RETRIES"])
        if "GEMINI_API_KEY" in merged and merged["GEMINI_API_KEY"]:
            kwargs["gemini_api_key"] = SecretStr(merged["GEMINI_API_KEY"])
        if "OLLAMA_HOST" in merged:
            kwargs["ollama_host"] = merged["OLLAMA_HOST"]

        return cls(**kwargs)


_cached_config: Optional[KanomanConfig] = None


def get_config(reload: bool = False) -> KanomanConfig:
    """Retrieve the singleton KanomanConfig instance."""
    global _cached_config
    if _cached_config is None or reload:
        _cached_config = KanomanConfig.from_env()
    return _cached_config
