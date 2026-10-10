"""Regression tests for Phase 7 independent security audit and hardening."""

import pytest
from pathlib import Path
from kanoman.ai.mock import MockAIProvider
from kanoman.ai.models import AIErrorType, AIException, AIMessage
from kanoman.ai.gemini import GeminiAIProvider
from kanoman.ai.router import AIRouter
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Project, Task, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry
from kanoman.git.controller import GitController


def test_git_controller_rejects_path_traversal_and_absolute_paths(tmp_path: Path):
    ctrl = GitController(
        workspace_root=tmp_path,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )

    with pytest.raises(ValueError, match="Path traversal detected"):
        ctrl.validate_target_file("../outside.txt")

    with pytest.raises(ValueError, match="Absolute file paths are prohibited"):
        ctrl.validate_target_file("C:/Windows/System32/calc.exe")


def test_git_controller_rejects_credential_file_names(tmp_path: Path):
    ctrl = GitController(
        workspace_root=tmp_path,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )

    with pytest.raises(ValueError, match="prohibited credential file"):
        ctrl.validate_target_file(".env")

    with pytest.raises(ValueError, match="prohibited credential file"):
        ctrl.validate_target_file(".env.production")

    with pytest.raises(ValueError, match="prohibited credential file"):
        ctrl.validate_target_file("deploy.key")

    with pytest.raises(ValueError, match="prohibited credential file"):
        ctrl.validate_target_file("server.pem")


def test_git_controller_blocks_destructive_flags_extended(tmp_path: Path):
    ctrl = GitController(
        workspace_root=tmp_path,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )

    with pytest.raises(ValueError, match="Prohibited destructive Git flag detected"):
        ctrl._run_git(["push", "--force-with-lease", "origin", "main"])

    with pytest.raises(ValueError, match="Destructive command 'git reset --hard' is strictly prohibited"):
        ctrl._run_git(["reset", "--merge", "HEAD~1"])

    with pytest.raises(ValueError, match="Destructive command 'git clean' is strictly prohibited"):
        ctrl._run_git(["clean", "-fdx"])


def test_recovery_rejects_path_traversal_in_checkpoint_id(tmp_path: Path):
    recovery = RecoveryEngine(tmp_path)

    with pytest.raises(ValueError, match="Invalid checkpoint_id format"):
        recovery.load_checkpoint("../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid checkpoint_id format"):
        recovery.load_checkpoint("chk_123/../../leak")


def test_orchestrator_rejects_executing_terminal_task(tmp_path: Path):
    config = KanomanConfig(checkpoint_dir=tmp_path / "checkpoints")
    orchestrator = TaskOrchestrator(config=config)

    task = Task(title="Done Task", description="Already finished task.")
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.COMPLETED)

    with pytest.raises(ValueError, match="Cannot execute task already in terminal state"):
        orchestrator.execute_task(task, task_type="ping")


def test_gemini_provider_uses_header_for_api_key():
    from pydantic import SecretStr

    dummy_key = "".join(["AI", "za", "x" * 35])
    gemini = GeminiAIProvider(api_key=SecretStr(dummy_key))
    assert gemini.health_check() is True
    # Verify endpoint does not leak key in query param
    assert "?key=" not in gemini.base_url


def test_ai_router_generate_structured_and_selective_fallback():
    failing_mock = MockAIProvider(name="flaky", simulate_error=AIErrorType.RATE_LIMIT_ERROR)
    healthy_mock = MockAIProvider(name="mock")

    router = AIRouter()
    router.register_provider(failing_mock)
    router.register_provider(healthy_mock)

    msgs = [AIMessage(role="user", content="Return structured data.")]
    res = router.generate_structured(msgs, schema={"type": "object"}, primary_name="flaky", fallback_name="mock")

    assert res.provider == "mock"
    assert res.structured_data is not None


def test_ai_router_does_not_fallback_on_client_validation_error():
    # If request is invalid (empty messages), fallback should NOT be invoked
    client_error_mock = MockAIProvider(name="primary", simulate_error=AIErrorType.VALIDATION_ERROR)
    healthy_mock = MockAIProvider(name="fallback")

    router = AIRouter()
    router.register_provider(client_error_mock)
    router.register_provider(healthy_mock)

    msgs = [AIMessage(role="user", content="Test")]
    with pytest.raises(AIException) as excinfo:
        router.generate_text(msgs, primary_name="primary", fallback_name="fallback")

    assert excinfo.value.error_type == AIErrorType.VALIDATION_ERROR
    assert healthy_mock.call_count == 0  # Fallback was not called


def test_project_registry_persistence_and_root_validation(tmp_path: Path):
    storage_file = tmp_path / "projects.json"
    registry1 = ProjectRegistry(storage_file=storage_file)

    proj_dir = tmp_path / "sub_project"
    proj_dir.mkdir()

    proj = Project(
        project_id="persistent_proj",
        name="Persistent Project",
        workspace_root=proj_dir,
        allowed_remote_url="https://github.com/qomaruddindjamal/kanoman.git",
    )
    registry1.register_project(proj)

    # Re-initialize registry from storage_file and verify persistence
    registry2 = ProjectRegistry(storage_file=storage_file)
    retrieved = registry2.get_project("persistent_proj")
    assert retrieved is not None
    assert retrieved.name == "Persistent Project"


def test_quality_gate_blocks_filesystem_symlink_escape(tmp_path: Path) -> None:
    import os
    from kanoman.agents.quality_gate import AgentQualityGate

    ws = tmp_path / "workspace"
    ws.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    target_file = outside_dir / "target.py"
    target_file.write_text("x = 100\n", encoding="utf-8")

    link_file = ws / "symlink_escape.py"
    try:
        os.symlink(target_file, link_file)
    except OSError:
        pytest.skip("Symlink creation not permitted in this OS environment.")

    gate = AgentQualityGate(workspace_root=ws)
    with pytest.raises(ValueError, match="resolves outside workspace root|Symlink escape detected"):
        gate.validate_target_path("symlink_escape.py")


def test_recovery_rejects_task_id_mismatch(tmp_path: Path) -> None:
    from kanoman.core.models import Checkpoint

    engine = RecoveryEngine(tmp_path)
    task = Task(task_id="task_genuine_01", title="Genuine Task", description="Testing mismatch.")
    chk_foreign = Checkpoint(
        task_id="task_foreign_99",
        project_id="kanoman",
        status=TaskStatus.RUNNING.value,
        change_summary="Foreign checkpoint payload.",
    )

    with pytest.raises(ValueError, match="Checkpoint task_id mismatch"):
        engine.resume_task(task, chk_foreign)


def test_recovery_rejects_terminal_task_resumption(tmp_path: Path) -> None:
    from kanoman.core.models import Checkpoint

    engine = RecoveryEngine(tmp_path)

    # Test COMPLETED task
    task_done = Task(task_id="task_done_01", title="Done Task", description="Testing terminal.")
    task_done.transition_to(TaskStatus.RUNNING)
    task_done.transition_to(TaskStatus.COMPLETED)
    chk = Checkpoint(task_id="task_done_01", status="COMPLETED", change_summary="Completed.")

    with pytest.raises(ValueError, match="Cannot resume a terminal task in status COMPLETED"):
        engine.resume_task(task_done, chk)

    # Test CANCELLED task
    task_cancelled = Task(task_id="task_cancel_01", title="Cancelled Task", description="Testing cancel.")
    task_cancelled.transition_to(TaskStatus.CANCELLED)
    chk_cancel = Checkpoint(task_id="task_cancel_01", status="CANCELLED", change_summary="Cancelled.")

    with pytest.raises(ValueError, match="Cannot resume a terminal task in status CANCELLED"):
        engine.resume_task(task_cancelled, chk_cancel)
