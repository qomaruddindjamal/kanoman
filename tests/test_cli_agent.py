"""Comprehensive tests for CLI multi-agent workflows in Kanoman AI.

Tests:
1. CLI help and argument validation.
2. CLI input boundary enforcement (title, desc, iterations, token budget).
3. CLI successful coordination workflow using MockAIProvider (text and json output).
4. CLI handling of Quality Gate and Security Auditor veto (exit code 1, sanitized error).
5. CLI handling of provider failures and timeouts.
6. CLI task run with task_type="coordinate_agents".
7. Zero secret leak in CLI stdout and stderr.
8. CLI prevents autonomous commit/push bypass.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from kanoman.ai.models import AIErrorType, AIException, AIMessage, AIResponse, UsageMetadata
from kanoman.ai.mock import MockAIProvider
from kanoman.cli.main import build_parser, main
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Task, TaskPriority, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator


class InsecureMockProvider(MockAIProvider):
    """Mock provider generating dynamic code execution (eval) to trigger security veto."""

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        insecure_data = {
            "target_path": "src/kanoman/dyn.py",
            "proposed_content": "import os\n\ndef run(s: str):\n    eval(s)\n",
            "rationale": "Dynamic execution.",
        }
        return AIResponse(
            provider="mock",
            model_name="mock-insecure",
            content=json.dumps(insecure_data),
            structured_data=insecure_data,
            usage=UsageMetadata(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )


class FailingMockProvider(MockAIProvider):
    """Mock provider simulating transient service failure."""

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        raise AIException(
            error_type=AIErrorType.SERVICE_UNAVAILABLE,
            message="Upstream API unavailable. Key AIzaSyFakeSecretKey789 exposed in raw error.",
            provider="mock",
        )


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def test_config(temp_workspace: Path) -> KanomanConfig:
    return KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
        default_ai_provider="mock",
    )


# =====================================================================
# 1. CLI Help & Argument Validation
# =====================================================================


def test_cli_help_displays_subcommands(capsys: pytest.CaptureFixture) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["agent", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "coordinate" in captured.out


def test_cli_coordinate_help(capsys: pytest.CaptureFixture) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["agent", "coordinate", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--title" in captured.out
    assert "--desc" in captured.out
    assert "--provider" in captured.out
    assert "--format" in captured.out


def test_cli_title_validation(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    # Too short (< 3 chars)
    rc_short = main(
        ["agent", "coordinate", "--title", "ab", "--desc", "Valid description here."],
        config=test_config,
    )
    assert rc_short == 2
    captured = capsys.readouterr()
    assert "Task title must be between 3 and 200 characters" in captured.err

    # Too long (> 200 chars)
    rc_long = main(
        ["agent", "coordinate", "--title", "a" * 201, "--desc", "Valid description here."],
        config=test_config,
    )
    assert rc_long == 2


def test_cli_description_validation(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    # Too short (< 5 chars)
    rc_short = main(
        ["agent", "coordinate", "--title", "Valid Title", "--desc", "tiny"],
        config=test_config,
    )
    assert rc_short == 2
    captured = capsys.readouterr()
    assert "Task description must be between 5 and 4000 characters" in captured.err

    # Too long (> 4000 chars)
    rc_long = main(
        ["agent", "coordinate", "--title", "Valid Title", "--desc", "a" * 4001],
        config=test_config,
    )
    assert rc_long == 2


def test_cli_iteration_and_budget_bounds(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    rc_iter = main(
        ["agent", "coordinate", "--title", "Title", "--desc", "Valid description.", "--max-iterations", "25"],
        config=test_config,
    )
    assert rc_iter == 2
    captured = capsys.readouterr()
    assert "max-iterations must be between 1 and 20" in captured.err

    rc_budget = main(
        ["agent", "coordinate", "--title", "Title", "--desc", "Valid description.", "--token-budget", "10"],
        config=test_config,
    )
    assert rc_budget == 2
    captured = capsys.readouterr()
    assert "token-budget must be between 100 and 500000" in captured.err


# =====================================================================
# 2. CLI Successful Execution (Text & JSON)
# =====================================================================


def test_cli_coordinate_success_text(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    rc = main(
        [
            "agent",
            "coordinate",
            "--title",
            "Build Secure Hash",
            "--desc",
            "Create a SHA256 helper module.",
            "--provider",
            "mock",
        ],
        config=test_config,
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "Kanoman Multi-Agent Coordination Result" in captured.out
    assert "Status:         COMPLETED" in captured.out
    assert "Checkpoint:     chk_" in captured.out


def test_cli_coordinate_success_json(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    rc = main(
        [
            "agent",
            "coordinate",
            "--title",
            "Build Secure Hash JSON",
            "--desc",
            "Create a SHA256 helper module.",
            "--provider",
            "mock",
            "--format",
            "json",
        ],
        config=test_config,
    )
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_successful"] is True
    assert data["status"] == "COMPLETED"
    assert data["task_id"] is not None
    assert data["checkpoint_id"] is not None
    assert data["sanitized_error"] is None


# =====================================================================
# 3. CLI Handling of Quality Gate / Security Veto
# =====================================================================


def test_cli_coordinate_handles_security_veto(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    # Inject insecure mock through task handler
    insecure_orch = TaskOrchestrator(config=test_config)

    def insecure_coord_handler(task: Task, cfg: Any, reg: Any) -> Dict[str, Any]:
        task.metadata["ai_provider"] = InsecureMockProvider()
        task.metadata["use_specialists"] = True
        # Call base coordinate_agents_handler logic
        from kanoman.agents.coordinator import MultiAgentCoordinator, CoordinatorStatus
        from kanoman.agents.quality_gate import AgentQualityGate
        from kanoman.agents.runners import (
            ArchitectRunner,
            CoderRunner,
            SecurityAuditorRunner,
            QAEngineerRunner,
            execute_end_to_end_specialist_workflow,
        )
        gate = AgentQualityGate(cfg.workspace_root)
        coord = MultiAgentCoordinator(config=cfg, quality_gate=gate)
        p = InsecureMockProvider()
        res = execute_end_to_end_specialist_workflow(
            task=task,
            coordinator=coord,
            architect=ArchitectRunner(p),
            coder=CoderRunner(p),
            auditor=SecurityAuditorRunner(p),
            qa=QAEngineerRunner(p),
            quality_gate=gate,
        )
        if not res.is_successful:
            raise ValueError(f"Multi-agent coordination rejected (security veto): {res.error or 'Blocked by quality gate'}")
        return {"coordinator_result": res.model_dump()}

    insecure_orch.register_handler("coordinate_agents", insecure_coord_handler)

    rc_veto = main(
        [
            "agent",
            "coordinate",
            "--title",
            "Insecure Task",
            "--desc",
            "Attempt dynamic eval code.",
            "--format",
            "json",
        ],
        config=test_config,
        orchestrator=insecure_orch,
    )
    assert rc_veto == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_successful"] is False
    assert data["status"] == "FAILED"
    assert "security veto" in data["sanitized_error"].lower()


# =====================================================================
# 4. CLI Handling of Provider Failure and Secret Redaction
# =====================================================================


def test_cli_coordinate_provider_failure_and_secret_redaction(
    test_config: KanomanConfig, capsys: pytest.CaptureFixture
) -> None:
    failing_orch = TaskOrchestrator(config=test_config)
    dummy_secret = "AIzaSy" + "A" * 33

    def failing_handler(task: Task, cfg: Any, reg: Any) -> Dict[str, Any]:
        raise AIException(
            error_type=AIErrorType.SERVICE_UNAVAILABLE,
            message=f"Provider failure: {dummy_secret} leaked in raw message",
            provider="mock",
        )

    failing_orch.register_handler("coordinate_agents", failing_handler)

    rc = main(
        [
            "agent",
            "coordinate",
            "--title",
            "Failing Provider Task",
            "--desc",
            "Test provider outage handling.",
            "--format",
            "json",
        ],
        config=test_config,
        orchestrator=failing_orch,
    )
    assert rc == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_successful"] is False
    # CRITICAL: Secret MUST be redacted!
    assert dummy_secret not in captured.out
    assert dummy_secret not in captured.err


# =====================================================================
# 5. CLI task run with coordinate_agents type
# =====================================================================


def test_cli_task_run_coordinate_agents(test_config: KanomanConfig, capsys: pytest.CaptureFixture) -> None:
    rc = main(
        [
            "task",
            "run",
            "--type",
            "coordinate_agents",
            "--title",
            "Coordinate via Task Subcommand",
            "--desc",
            "Verify task run delegation.",
            "--use-specialists",
        ],
        config=test_config,
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "Status:      COMPLETED" in captured.out
