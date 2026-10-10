import pytest
from pathlib import Path
from kanoman.core.models import Task, TaskStatus, TaskPriority, Project, Checkpoint


def test_task_valid_lifecycle():
    task = Task(title="Initial Task", description="Testing task lifecycle flow.")
    assert task.status == TaskStatus.PENDING

    task.transition_to(TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING

    task.transition_to(TaskStatus.COMPLETED)
    assert task.status == TaskStatus.COMPLETED


def test_task_illegal_state_transition_fails():
    task = Task(title="Failed Task", description="Testing invalid FSM transition.")
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.FAILED, error="Some error occurred")

    # Direct FAILED -> COMPLETED is prohibited without RETRYING
    with pytest.raises(ValueError, match="Illegal state transition"):
        task.transition_to(TaskStatus.COMPLETED)


def test_project_rejects_credentials_in_fields():
    dummy_token = "gh" + "o_" + ("a" * 25)
    with pytest.raises(ValueError, match="Credentials must NEVER be stored"):
        Project(
            project_id="proj_1",
            name=f"Testing {dummy_token} leak",
            workspace_root=Path("c:/kanoman"),
            allowed_remote_url="https://github.com/qomaruddindjamal/kanoman.git",
        )


def test_checkpoint_sanitizes_change_summary():
    dummy_key = "s" + "k-" + ("b" * 25)
    chk = Checkpoint(
        task_id="task_1",
        status="COMPLETED",
        change_summary=f"Committed with key {dummy_key}",
    )
    assert "s" + "k-" not in chk.change_summary
    assert "***REDACTED_SECRET***" in chk.change_summary
