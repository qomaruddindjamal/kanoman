"""Data models for Git operations and state validation."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


class GitOperationMode(str, Enum):
    INSPECT = "inspect"
    DRY_RUN = "dry-run"
    COMMIT = "commit"
    PUSH = "push"


class GitStatusResult(BaseModel):
    """Snapshot of repository status from Git inspection."""

    root_path: Path
    current_branch: str
    remote_url: Optional[str] = None
    is_clean: bool
    staged_files: List[str] = Field(default_factory=list)
    unstaged_files: List[str] = Field(default_factory=list)
    untracked_files: List[str] = Field(default_factory=list)
    latest_commit_sha: Optional[str] = None
    latest_commit_message: Optional[str] = None


class GitOperationPlan(BaseModel):
    """Plan for planned Git operations in dry-run or commit mode."""

    mode: GitOperationMode
    target_branch: str
    files_to_stage: List[str]
    commit_message: str
    push_target: Optional[str] = None
    is_safe: bool = True
    warnings: List[str] = Field(default_factory=list)


class CommitResult(BaseModel):
    """Outcome of a commit operation."""

    success: bool
    mode: GitOperationMode
    commit_sha: Optional[str] = None
    message: str
    staged_count: int = 0
    pushed: bool = False
    details: Optional[str] = None
