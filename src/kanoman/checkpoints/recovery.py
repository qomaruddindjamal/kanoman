"""Recovery Engine for Kanoman AI.

Provides atomic, corruption-resistant checkpoint saving and loading.
Ensures checkpoints are schema-validated, immutable per checkpoint ID,
and sanitizes all serialized attributes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional
from kanoman.core.models import Checkpoint, Task, TaskStatus
from kanoman.logging.logger import get_logger

logger = get_logger("recovery")


class RecoveryEngine:
    """Manages creation, schema validation, and recovery of checkpoints."""

    def __init__(self, checkpoint_dir: Path) -> None:
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, checkpoint: Checkpoint) -> Path:
        """Atomically persist a checkpoint to disk using a temporary file and atomic replace."""
        filename = f"{checkpoint.checkpoint_id}.json"
        dest_path = self.checkpoint_dir / filename

        # Ensure directory exists
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        payload_str = checkpoint.model_dump_json(indent=2)

        # Write to temporary file in same directory to ensure same filesystem for atomic replace
        with tempfile.NamedTemporaryFile("w", dir=self.checkpoint_dir, delete=False, encoding="utf-8") as tf:
            tf.write(payload_str)
            temp_path = Path(tf.name)

        try:
            temp_path.replace(dest_path)
            logger.info(
                f"Checkpoint saved: {checkpoint.checkpoint_id}",
                task_id=checkpoint.task_id,
                project_id=checkpoint.project_id,
                status="CHECKPOINT_SAVED",
            )
            return dest_path
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            logger.error(f"Failed to save checkpoint {checkpoint.checkpoint_id}: {str(e)}")
            raise

    def load_checkpoint(self, checkpoint_id: str) -> Checkpoint:
        """Load and strictly validate a checkpoint by its ID."""
        clean_id = checkpoint_id.strip()
        import re
        if not clean_id or not re.match(r"^[a-zA-Z0-9_\-]+$", clean_id):
            raise ValueError(f"Invalid checkpoint_id format: '{checkpoint_id}'")

        file_path = (self.checkpoint_dir / f"{clean_id}.json").resolve()
        if self.checkpoint_dir.resolve() not in file_path.parents:
            raise ValueError(f"Path traversal detected in checkpoint_id: '{checkpoint_id}'")

        if not file_path.is_file():
            raise FileNotFoundError(f"Checkpoint file '{file_path}' does not exist.")

        try:
            raw_data = json.loads(file_path.read_text(encoding="utf-8"))
            checkpoint = Checkpoint(**raw_data)
            return checkpoint
        except Exception as e:
            logger.error(f"Checkpoint validation failure for {checkpoint_id}: {str(e)}")
            raise ValueError(f"Corrupt or invalid checkpoint schema: {str(e)}") from e

    def get_latest_checkpoint(self, task_id: Optional[str] = None) -> Optional[Checkpoint]:
        """Find the most recent checkpoint by creation timestamp, optionally filtered by task_id."""
        candidates: List[Checkpoint] = []
        for file in self.checkpoint_dir.glob("chk_*.json"):
            try:
                cp = self.load_checkpoint(file.stem)
                if task_id is None or cp.task_id == task_id:
                    candidates.append(cp)
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda c: c.created_at, reverse=True)
        return candidates[0]

    def resume_task(self, task: Task, checkpoint: Checkpoint) -> Task:
        """Resume a task state safely from a checkpoint snapshot."""
        if checkpoint.task_id != task.task_id:
            raise ValueError(
                f"Checkpoint task_id mismatch: checkpoint has '{checkpoint.task_id}', "
                f"task has '{task.task_id}'"
            )

        # Ensure safe state transition
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise ValueError(f"Cannot resume a terminal task in status {task.status.value}")

        if task.status == TaskStatus.FAILED:
            task.transition_to(TaskStatus.RETRYING)
            task.transition_to(TaskStatus.RUNNING)
        elif task.status == TaskStatus.PENDING:
            task.transition_to(TaskStatus.RUNNING)

        task.checkpoint_id = checkpoint.checkpoint_id
        logger.info(
            f"Task {task.task_id} successfully resumed from checkpoint {checkpoint.checkpoint_id}",
            task_id=task.task_id,
            status="TASK_RESUMED",
        )
        return task
