"""End-to-End Integration and Failure Resilience Tests for Kanoman AI.

Validates the entire lifecycle:
1. Load & validate configuration
2. Register project in ProjectRegistry
3. Create & validate Task
4. Orchestrator executes task via handler & Mock AI Provider
5. Store task results and generate atomic Checkpoint
6. RecoveryEngine loads and verifies checkpoint integrity
7. GitController inspects repository and performs dry-run plan
8. Verifies failure modes and security barriers
"""

import subprocess
import pytest
from pathlib import Path
from kanoman.ai.mock import MockAIProvider
from kanoman.ai.models import AIMessage
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Project, Task, TaskPriority, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry
from kanoman.git.controller import GitController
from kanoman.git.models import GitOperationMode


@pytest.fixture
def e2e_workspace(tmp_path: Path):
    """Fixture providing a simulated test repository and isolated checkpoint directory."""
    repo_dir = tmp_path / "e2e_repo"
    repo_dir.mkdir()
    chk_dir = tmp_path / "checkpoints"
    chk_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "E2E Tester"], cwd=str(repo_dir), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "e2e@kanoman.local"],
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

    return {"repo_dir": repo_dir, "chk_dir": chk_dir}


def test_complete_end_to_end_orchestration_cycle(e2e_workspace: dict):
    repo_dir = e2e_workspace["repo_dir"]
    chk_dir = e2e_workspace["chk_dir"]

    # Step 1 & 2: Load and validate configuration
    config = KanomanConfig(
        workspace_root=repo_dir,
        checkpoint_dir=chk_dir,
        git_dry_run=True,
        git_allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
        default_ai_provider="mock",
    )
    assert config.git_dry_run is True

    # Step 3: Register test project
    registry = ProjectRegistry()
    project = Project(
        project_id="e2e_project",
        name="End-to-End Test Project",
        workspace_root=repo_dir,
        allowed_remote_url=config.git_allowed_remote,
        policy_branch="main",
    )
    registry.register_project(project)
    assert registry.get_project("e2e_project") is not None

    # Step 4: AI Provider integration
    ai_mock = MockAIProvider(default_reply="E2E Architecture analysis passed.")
    ai_response = ai_mock.generate_text([AIMessage(role="user", content="Analyze E2E architecture.")])
    assert ai_response.content == "E2E Architecture analysis passed."

    # Step 5: Orchestrator executes task
    recovery = RecoveryEngine(chk_dir)
    orchestrator = TaskOrchestrator(config=config, registry=registry, recovery_engine=recovery)

    # Register custom handler that leverages the AI response
    def custom_ai_task_handler(task: Task, cfg: KanomanConfig, reg: ProjectRegistry):
        return {
            "message": ai_response.content,
            "test_results": {"passed": 10, "failed": 0},
            "next_steps": ["Proceed to git dry-run verification"],
        }

    orchestrator.register_handler("ai_analysis", custom_ai_task_handler)

    task = Task(
        title="E2E Full Orchestration",
        description="Verify end-to-end task execution with AI and recovery.",
        project_id="e2e_project",
        priority=TaskPriority.HIGH,
    )
    completed_task = orchestrator.execute_task(task, task_type="ai_analysis")

    # Step 6 & 7: Verify task completed and checkpoint created
    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.checkpoint_id is not None
    assert completed_task.result_summary == "E2E Architecture analysis passed."

    # Step 8: Recovery Engine verifies checkpoint
    loaded_chk = recovery.load_checkpoint(completed_task.checkpoint_id)
    assert loaded_chk.task_id == completed_task.task_id
    assert loaded_chk.project_id == "e2e_project"
    assert loaded_chk.test_results["passed"] == 10

    # Step 9: Git Controller inspects repository
    git_ctrl = GitController(
        workspace_root=repo_dir,
        allowed_remote=config.git_allowed_remote,
        allowed_branches=["main"],
        config=config,
    )
    status = git_ctrl.inspect()
    assert status.current_branch == "main"
    assert status.is_clean is True

    # Step 10: Create file and execute Dry-Run
    change_file = repo_dir / "CHANGELOG_E2E.md"
    change_file.write_text("# E2E Changelog Entry\n", encoding="utf-8")

    plan = git_ctrl.dry_run(["CHANGELOG_E2E.md"], "chore: e2e test log")
    assert plan.mode == GitOperationMode.DRY_RUN
    assert plan.is_safe is True
    assert "CHANGELOG_E2E.md" in plan.files_to_stage

    # Verify dry-run did not alter git commit state
    status_post = git_ctrl.inspect()
    assert status_post.latest_commit_sha is None
    assert "CHANGELOG_E2E.md" in status_post.untracked_files


def test_failure_handling_and_security_barriers(e2e_workspace: dict):
    repo_dir = e2e_workspace["repo_dir"]
    chk_dir = e2e_workspace["chk_dir"]

    config = KanomanConfig(workspace_root=repo_dir, checkpoint_dir=chk_dir)
    git_ctrl = GitController(
        workspace_root=repo_dir,
        allowed_remote=config.git_allowed_remote,
        config=config,
    )

    # Barrier 1: Leak attempt is caught and blocked
    leak_file = repo_dir / "secret.env"
    dummy_key = "s" + "k-" + ("a" * 25)
    leak_file.write_text(f"API_SECRET={dummy_key}\n", encoding="utf-8")

    plan = git_ctrl.dry_run(["secret.env"], "Accidental leak commit")
    assert plan.is_safe is False
    assert any("Secret detected" in w for w in plan.warnings)

    # Barrier 2: Corrupted checkpoint loading fails safely
    recovery = RecoveryEngine(chk_dir)
    bad_file = chk_dir / "chk_bad.json"
    bad_file.write_text("invalid json structure", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt or invalid checkpoint schema"):
        recovery.load_checkpoint("chk_bad")
