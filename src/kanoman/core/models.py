"""Domain models for Kanoman AI.

Implements Task, Project, and Checkpoint models with strict Pydantic v2 validation,
deterministic FSM state transitions, and credential sanitization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Permitted state transitions for task lifecycle integrity
VALID_STATE_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.RETRYING},
    TaskStatus.RETRYING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.FAILED: {TaskStatus.RETRYING, TaskStatus.CANCELLED},  # Cannot jump straight to COMPLETED
    TaskStatus.COMPLETED: set(),  # Terminal state
    TaskStatus.CANCELLED: set(),  # Terminal state
}


class Task(BaseModel):
    """Represents a unit of work within the Kanoman Orchestrator."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=5, max_length=5000)
    project_id: Optional[str] = Field(default=None)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acceptance_criteria: List[str] = Field(default_factory=list)
    result_summary: Optional[str] = Field(default=None)
    checkpoint_id: Optional[str] = Field(default=None)
    sanitized_error: Optional[str] = Field(default=None)

    def transition_to(self, new_status: TaskStatus, error: Optional[str] = None) -> None:
        """Enforce deterministic state transitions and timestamp update."""
        allowed = VALID_STATE_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal state transition from {self.status.value} to {new_status.value}. "
                f"Permitted next states: {[s.value for s in allowed]}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        if error:
            # Sanitize error string
            from kanoman.logging.logger import redact_sensitive_text
            self.sanitized_error = redact_sensitive_text(error)


class Project(BaseModel):
    """Represents a registered codebase project managed by Kanoman."""

    project_id: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=100)
    workspace_root: Path
    allowed_remote_url: str
    policy_branch: str = Field(default="main")
    is_registered: bool = Field(default=True)
    test_command: str = Field(default="python -m pytest")
    git_dry_run_policy: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("workspace_root", mode="before")
    @classmethod
    def validate_workspace(cls, v: Any) -> Path:
        p = Path(v).resolve()
        return p

    @field_validator("allowed_remote_url")
    @classmethod
    def validate_remote(cls, v: str) -> str:
        clean = v.strip()
        if not (clean.startswith("https://") or clean.startswith("git@")):
            raise ValueError(f"Invalid remote URL format: {clean}")
        return clean

    @model_validator(mode="after")
    def reject_credentials(self) -> Project:
        """Ensure no auth tokens are embedded in project fields."""
        for field_val in [self.project_id, self.name, self.allowed_remote_url]:
            if any(token in field_val.lower() for token in ["gho_", "ghp_", "sk-", "password="]):
                raise ValueError("Credentials must NEVER be stored in Project definitions.")
        return self


class Checkpoint(BaseModel):
    """Snapshot representation of task and git state at a given point in time."""

    checkpoint_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:12]}")
    task_id: str
    project_id: Optional[str] = None
    status: str
    change_summary: str
    test_results: Optional[Dict[str, Any]] = None
    next_steps: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    git_commit_sha: Optional[str] = None
    git_branch: Optional[str] = None

    @field_validator("checkpoint_id", "task_id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        clean = v.strip()
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]+$", clean):
            raise ValueError(f"Invalid characters in identifier: '{clean}'")
        return clean

    @model_validator(mode="after")
    def sanitize_metadata(self) -> Checkpoint:
        from kanoman.logging.logger import redact_sensitive_text
        self.change_summary = redact_sensitive_text(self.change_summary)
        return self
