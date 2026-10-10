import pytest
from pathlib import Path
from kanoman.config.settings import KanomanConfig, EnvironmentType


def test_default_config_is_safe():
    config = KanomanConfig()
    assert config.env == EnvironmentType.DEVELOPMENT
    assert config.git_dry_run is True
    assert config.default_ai_provider == "mock"
    assert config.ai_timeout_seconds == 30
    assert config.gemini_api_key is None


def test_config_masks_secrets_in_safe_dump():
    config = KanomanConfig(
        gemini_api_key="AIzaSyTestKey123456789012345678901234",
    )
    safe_dump = config.model_dump_safe()
    assert safe_dump["gemini_api_key"] == "***REDACTED***"


def test_config_rejects_invalid_remote_url():
    with pytest.raises(ValueError, match="Remote URL must start with"):
        KanomanConfig(git_allowed_remote="ftp://invalid.com/repo.git")


def test_config_rejects_unsupported_ai_provider():
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        KanomanConfig(default_ai_provider="unsupported_vendor")
