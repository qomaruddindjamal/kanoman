import pytest
from pathlib import Path
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.core.models import Checkpoint, Task, TaskStatus


def test_atomic_checkpoint_save_and_load(tmp_path: Path):
    engine = RecoveryEngine(tmp_path)
    chk = Checkpoint(
        task_id="task_abc",
        project_id="kanoman",
        status="COMPLETED",
        change_summary="All tests passing.",
        test_results={"passed": 5, "failed": 0},
    )
    dest_path = engine.save_checkpoint(chk)
    assert dest_path.is_file()

    loaded = engine.load_checkpoint(chk.checkpoint_id)
    assert loaded.checkpoint_id == chk.checkpoint_id
    assert loaded.task_id == "task_abc"
    assert loaded.test_results["passed"] == 5


def test_recovery_rejects_corrupted_checkpoint(tmp_path: Path):
    engine = RecoveryEngine(tmp_path)
    corrupted_file = tmp_path / "chk_corrupted.json"
    corrupted_file.write_text("{invalid_json: true", encoding="utf-8")

    with pytest.raises(ValueError, match="Corrupt or invalid checkpoint schema"):
        engine.load_checkpoint("chk_corrupted")


def test_resume_task_safe_state_transition(tmp_path: Path):
    engine = RecoveryEngine(tmp_path)
    task = Task(title="Resume Test", description="Testing recovery transition.")
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.FAILED, error="Network glitch")

    chk = Checkpoint(
        task_id=task.task_id,
        status="FAILED",
        change_summary="Execution failed temporarily.",
    )
    engine.save_checkpoint(chk)

    resumed_task = engine.resume_task(task, chk)
    assert resumed_task.status == TaskStatus.RUNNING
    assert resumed_task.checkpoint_id == chk.checkpoint_id


def test_resume_task_succeeds_with_matching_project_id(tmp_path: Path):
    engine = RecoveryEngine(tmp_path)
    task = Task(
        title="Resume Match",
        description="Testing matching project_id resume.",
        project_id="proj_alpha",
    )
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.FAILED, error="Transient error")

    chk = Checkpoint(
        task_id=task.task_id,
        project_id="proj_alpha",
        status="FAILED",
        change_summary="Temporary failure.",
    )
    engine.save_checkpoint(chk)

    resumed = engine.resume_task(task, chk)
    assert resumed.status == TaskStatus.RUNNING
    assert resumed.project_id == "proj_alpha"
    assert resumed.checkpoint_id == chk.checkpoint_id


def test_resume_task_rejects_mismatched_project_id_fail_closed(tmp_path: Path):
    engine = RecoveryEngine(tmp_path)
    task = Task(
        title="Resume Mismatch",
        description="Testing mismatched project_id resume.",
        project_id="proj_kanoman",
    )
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.FAILED, error="Failure")

    chk = Checkpoint(
        task_id=task.task_id,
        project_id="proj_mitranet",
        status="FAILED",
        change_summary="Failure under another project.",
    )
    engine.save_checkpoint(chk)

    with pytest.raises(ValueError, match="Checkpoint project_id mismatch.*Fail-closed"):
        engine.resume_task(task, chk)

    # Invariant: Task state must NOT be modified on rejection
    assert task.status == TaskStatus.FAILED
    assert task.checkpoint_id is None


def test_resume_task_rejects_none_vs_defined_project_id_fail_closed(tmp_path: Path):
    engine = RecoveryEngine(tmp_path)

    # Case 1: Task has project_id, but checkpoint has None (e.g. legacy/foreign)
    task1 = Task(
        title="Task Defined",
        description="Task with project_id defined.",
        project_id="proj_beta",
    )
    task1.transition_to(TaskStatus.RUNNING)
    task1.transition_to(TaskStatus.FAILED, error="Err")

    chk_legacy = Checkpoint(
        task_id=task1.task_id,
        project_id=None,
        status="FAILED",
        change_summary="Legacy checkpoint without project_id.",
    )
    with pytest.raises(ValueError, match="Checkpoint project_id mismatch.*Fail-closed"):
        engine.resume_task(task1, chk_legacy)
    assert task1.status == TaskStatus.FAILED

    # Case 2: Task has None, but checkpoint has project_id
    task2 = Task(
        title="Task None",
        description="Task without project_id.",
        project_id=None,
    )
    task2.transition_to(TaskStatus.RUNNING)
    task2.transition_to(TaskStatus.FAILED, error="Err")

    chk_defined = Checkpoint(
        task_id=task2.task_id,
        project_id="proj_gamma",
        status="FAILED",
        change_summary="Checkpoint with project_id.",
    )
    with pytest.raises(ValueError, match="Checkpoint project_id mismatch.*Fail-closed"):
        engine.resume_task(task2, chk_defined)
    assert task2.status == TaskStatus.FAILED
