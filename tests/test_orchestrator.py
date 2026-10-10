from pathlib import Path
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Task, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry


def test_orchestrator_executes_ping_task(tmp_path: Path):
    config = KanomanConfig(checkpoint_dir=tmp_path / "checkpoints")
    recovery = RecoveryEngine(config.checkpoint_dir)
    registry = ProjectRegistry()
    orchestrator = TaskOrchestrator(config=config, registry=registry, recovery_engine=recovery)

    task = Task(title="Ping Check", description="Checking orchestrator health.")
    finished_task = orchestrator.execute_task(task, task_type="ping")

    assert finished_task.status == TaskStatus.COMPLETED
    assert "Kanoman Core alive" in (finished_task.result_summary or "")
    assert finished_task.checkpoint_id is not None

    # Verify checkpoint exists
    chk = recovery.load_checkpoint(finished_task.checkpoint_id)
    assert chk.status == "COMPLETED"


def test_orchestrator_handles_unsupported_task(tmp_path: Path):
    config = KanomanConfig(checkpoint_dir=tmp_path / "checkpoints")
    orchestrator = TaskOrchestrator(config=config)

    task = Task(title="Unknown Task", description="Executing an unregistered task type.")
    failed_task = orchestrator.execute_task(task, task_type="non_existent_handler")

    assert failed_task.status == TaskStatus.FAILED
    assert "Unsupported task type" in (failed_task.result_summary or "")
