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
