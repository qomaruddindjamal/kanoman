"""Comprehensive unit and integration tests for Quality Gate, GitController Veto, and TaskOrchestrator integration."""

import os
import subprocess
from pathlib import Path
from typing import Dict
import pytest

from kanoman.agents.coordinator import (
    CoordinatorResult,
    CoordinatorStatus,
    MultiAgentCoordinator,
)
from kanoman.agents.models import (
    AgentDecision,
    AgentPlan,
    AgentPlanStep,
    AgentRole,
    DecisionType,
)
from kanoman.agents.quality_gate import AgentQualityGate, QualityGateResult
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Checkpoint, Task, TaskPriority, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.git.controller import GitController


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "git_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@kanoman.local"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/qomaruddindjamal/kanoman.git"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    return repo_dir


# =====================================================================
# 1. Quality Gate: Valid and Invalid Proposals
# =====================================================================

def test_quality_gate_valid_python_proposal(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    code = "def safe_function(x: int) -> int:\n    return x * 2\n"
    result: QualityGateResult = gate.verify_proposal("task_1", "src/safe.py", code)

    assert result.is_approved is True
    assert result.decision.decision_type == DecisionType.APPROVE
    assert result.file_type == "python"
    assert len(result.findings) == 0


def test_quality_gate_blocks_vulnerable_python_proposal(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    bad_code = "eval('__import__(\"os\").system(\"calc\")')\n"
    result: QualityGateResult = gate.verify_proposal("task_1", "src/vuln.py", bad_code)

    assert result.is_approved is False
    assert result.decision.decision_type == DecisionType.REJECT
    assert any(f.rule_id == "PY_EVAL_EXEC" for f in result.findings)
    assert "blocking finding" in result.decision.rationale


def test_quality_gate_blocks_invalid_markdown_proposal(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    bad_md = "# Title\n\n```python\nprint('unclosed fence')\n"
    result: QualityGateResult = gate.verify_proposal("task_1", "docs/broken.md", bad_md)

    assert result.is_approved is False
    assert result.decision.decision_type == DecisionType.REJECT
    assert any(f.rule_id == "MD_UNCLOSED_FENCE" for f in result.findings)


# =====================================================================
# 2. Quality Gate: Fail-Closed & Path Validation
# =====================================================================

def test_quality_gate_fail_closed_on_unsupported_extension(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    result = gate.verify_proposal("task_1", "scripts/run.sh", "echo 'hello'")

    assert result.is_approved is False
    assert result.decision.decision_type == DecisionType.REJECT
    assert "Unsupported file extension" in result.decision.rationale


def test_quality_gate_rejects_path_traversal(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    result = gate.verify_proposal("task_1", "../outside.py", "x = 1")

    assert result.is_approved is False
    assert result.decision.decision_type == DecisionType.REJECT
    assert "Path traversal detected" in result.decision.rationale


def test_quality_gate_rejects_absolute_path(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    abs_path = "C:/Windows/System32/calc.py" if os.name == "nt" else "/etc/passwd.py"
    result = gate.verify_proposal("task_1", abs_path, "x = 1")

    assert result.is_approved is False
    assert result.decision.decision_type == DecisionType.REJECT
    assert "Absolute paths are prohibited" in result.decision.rationale


# =====================================================================
# 3. Coordinator GitController Veto & Authorization
# =====================================================================

def test_coordinator_git_dry_run_does_not_mutate(temp_git_repo: Path):
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    coordinator = MultiAgentCoordinator(git_controller=ctrl)
    coordinator.current_task_id = "task_git_001"

    test_file = temp_git_repo / "doc.txt"
    test_file.write_text("Proposed documentation", encoding="utf-8")

    plan = coordinator.request_git_operation("dry-run", files=["doc.txt"], message="Simulate doc add")
    assert plan.is_safe is True

    # Confirm working tree remains uncommitted
    inspect_status = ctrl.inspect()
    assert inspect_status.latest_commit_sha is None
    assert "doc.txt" in inspect_status.untracked_files


def test_coordinator_prohibits_autonomous_commit_or_push(temp_git_repo: Path):
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    coordinator = MultiAgentCoordinator(git_controller=ctrl)
    coordinator.current_task_id = "task_git_002"

    with pytest.raises(PermissionError, match="Autonomous Git operation mode 'commit' is strictly prohibited"):
        coordinator.request_git_operation("commit", files=["a.py"], message="Unauthorized commit")

    with pytest.raises(PermissionError, match="Autonomous Git operation mode 'push' is strictly prohibited"):
        coordinator.request_git_operation("push")


def test_coordinator_git_security_veto_aborts_coordination(temp_git_repo: Path):
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    coordinator = MultiAgentCoordinator(git_controller=ctrl)
    coordinator.current_task_id = "task_git_003"

    # Attempt dry-run with path traversal
    with pytest.raises(PermissionError, match="GitController security veto triggered"):
        coordinator.request_git_operation("dry-run", files=["../escape.py"], message="Bad path")

    # Coordinator must enter ABORTED status
    assert coordinator.status == CoordinatorStatus.ABORTED
    assert any(d.decision_type == DecisionType.ABORT for d in coordinator.decisions)


def test_coordinator_unauthorized_remote_blocks_git_operation(tmp_path: Path):
    repo_dir = tmp_path / "bad_remote_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/malicious/repo.git"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )

    ctrl = GitController(
        workspace_root=repo_dir,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    coordinator = MultiAgentCoordinator(git_controller=ctrl)
    coordinator.current_task_id = "task_git_004"

    with pytest.raises(ValueError, match="Remote URL mismatch"):
        coordinator.request_git_operation("inspect")


# =====================================================================
# 4. TaskOrchestrator Integration & Lifecycle Mapping
# =====================================================================

def test_task_orchestrator_successful_coordination(temp_workspace: Path):
    config = KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
    )
    orchestrator = TaskOrchestrator(config=config)

    step1 = AgentPlanStep(
        step_id="step_arch",
        assigned_role=AgentRole.ARCHITECT,
        title="Architecture Review",
        description="Review core specifications",
    )
    plan = AgentPlan(
        task_id="task_orch_001",
        goal="Perform architecture review",
        steps=[step1],
    )

    task = Task(
        task_id="task_orch_001",
        title="Review Task",
        description="Verify architecture integrity",
        metadata={"plan": plan.model_dump()},
    )

    result_task = orchestrator.execute_task(task, task_type="coordinate_agents")

    assert result_task.status == TaskStatus.COMPLETED
    assert "Multi-agent coordination completed successfully" in (result_task.result_summary or "")
    assert result_task.checkpoint_id is not None


def test_task_orchestrator_handles_rejected_coordination(temp_workspace: Path):
    config = KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
    )
    orchestrator = TaskOrchestrator(config=config)

    # Custom handler that rejects step
    def reject_handler(task: Task, cfg: KanomanConfig, reg) -> Dict:
        raise ValueError("Multi-agent coordination rejected: Code quality gate blocked proposal.")

    orchestrator.register_handler("coordinate_agents", reject_handler)

    task = Task(
        task_id="task_orch_002",
        title="Rejected Task",
        description="Task designed to fail",
    )

    result_task = orchestrator.execute_task(task, task_type="coordinate_agents")

    assert result_task.status == TaskStatus.FAILED
    assert "Code quality gate blocked proposal" in (result_task.result_summary or "")
    assert result_task.checkpoint_id is not None


def test_task_orchestrator_handles_aborted_coordination(temp_workspace: Path):
    config = KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
    )
    orchestrator = TaskOrchestrator(config=config)

    def abort_handler(task: Task, cfg: KanomanConfig, reg) -> Dict:
        raise ValueError("Multi-agent coordination aborted (security veto): Prohibited secret leak.")

    orchestrator.register_handler("coordinate_agents", abort_handler)

    task = Task(
        task_id="task_orch_003",
        title="Aborted Task",
        description="Task aborted by security veto",
    )

    result_task = orchestrator.execute_task(task, task_type="coordinate_agents")

    assert result_task.status == TaskStatus.FAILED
    assert "security veto" in (result_task.result_summary or "")


# =====================================================================
# 5. Recovery & Secret Leak Prevention
# =====================================================================

def test_recovery_preserves_quality_gate_audit(temp_workspace: Path):
    recovery = RecoveryEngine(checkpoint_dir=temp_workspace / ".kanoman_checkpoints")
    chk = Checkpoint(
        task_id="task_audit_001",
        status="RUNNING",
        change_summary="Step 1 evaluated by Quality Gate",
        test_results={
            "quality_gate": {
                "target_path": "src/module.py",
                "is_approved": True,
                "findings_count": 0,
            }
        },
    )
    recovery.save_checkpoint(chk)

    loaded = recovery.load_checkpoint(chk.checkpoint_id)
    assert loaded.test_results is not None
    assert loaded.test_results["quality_gate"]["target_path"] == "src/module.py"
    assert loaded.test_results["quality_gate"]["is_approved"] is True


def test_quality_gate_masks_secrets_in_error_and_rationale(temp_workspace: Path):
    gate = AgentQualityGate(workspace_root=temp_workspace)
    dummy_token = "gh" + "p_" + ("a" * 25)
    bad_code = f"api_key = '{dummy_token}'\n"

    result = gate.verify_proposal("task_sec_001", "src/secret.py", bad_code)

    assert dummy_token not in result.decision.rationale
    assert result.is_approved is False
    assert any(f.rule_id == "PY_HARDCODED_SECRET" for f in result.findings)
