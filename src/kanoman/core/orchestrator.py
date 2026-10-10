"""Task Orchestrator for Kanoman AI.

Executes tasks through an extensible handler registry, generates atomic checkpoints,
enforces deterministic FSM state transitions, and records structured, sanitized telemetry.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional
from kanoman.config.settings import KanomanConfig, get_config
from kanoman.core.models import Checkpoint, Task, TaskStatus
from kanoman.core.registry import ProjectRegistry
from kanoman.logging.logger import get_logger

if TYPE_CHECKING:
    from kanoman.checkpoints.recovery import RecoveryEngine

logger = get_logger("orchestrator")

# Task Handler Signature: Callable[[Task, KanomanConfig, ProjectRegistry], Dict[str, Any]]
TaskHandler = Callable[[Task, KanomanConfig, ProjectRegistry], Dict[str, Any]]


class TaskOrchestrator:
    """Deterministic orchestrator managing task lifecycle, execution, and checkpoints."""

    def __init__(
        self,
        config: Optional[KanomanConfig] = None,
        registry: Optional[ProjectRegistry] = None,
        recovery_engine: Optional[RecoveryEngine] = None,
    ) -> None:
        from kanoman.checkpoints.recovery import RecoveryEngine as _RecoveryEngine

        self.config = config or get_config()
        self.registry = registry or ProjectRegistry()
        self.recovery = recovery_engine or _RecoveryEngine(self.config.checkpoint_dir)
        self._handlers: Dict[str, TaskHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register built-in safe task handlers."""

        def ping_handler(task: Task, config: KanomanConfig, registry: ProjectRegistry) -> Dict[str, Any]:
            return {
                "message": "Kanoman Core alive and operational.",
                "env": config.env.value,
                "workspace": str(config.workspace_root),
            }

        def inspect_workspace_handler(
            task: Task, config: KanomanConfig, registry: ProjectRegistry
        ) -> Dict[str, Any]:
            root = config.workspace_root
            exists = root.is_dir()
            return {
                "workspace_root": str(root),
                "is_dir": exists,
                "project_count": len(registry.list_projects()),
            }

        def analyze_python_handler(
            task: Task, config: KanomanConfig, registry: ProjectRegistry
        ) -> Dict[str, Any]:
            from pathlib import Path
            from kanoman.analysis.python_analyzer import PythonASTAnalyzer

            analyzer = PythonASTAnalyzer(workspace_root=config.workspace_root)
            raw_target = task.metadata.get("target_path") if task.metadata else None
            target = Path(raw_target) if raw_target else config.workspace_root
            if not target.is_absolute():
                target = (config.workspace_root / target).resolve()

            if target.is_file():
                findings = analyzer.analyze_file(target)
                report_dict = {
                    "analyzer": "PythonASTAnalyzer",
                    "files_scanned": 1,
                    "findings_count": len(findings),
                    "findings": [f.model_dump() for f in findings],
                }
            else:
                report = analyzer.analyze_directory(target)
                report_dict = {
                    "analyzer": report.analyzer_name,
                    "files_scanned": report.files_scanned,
                    "findings_count": len(report.findings),
                    "summary_by_severity": report.summary_by_severity,
                    "findings": [f.model_dump() for f in report.findings],
                }

            msg = (
                f"Python AST analysis completed: {report_dict['files_scanned']} file(s) scanned, "
                f"{report_dict['findings_count']} finding(s)."
            )
            return {
                "message": msg,
                "report": report_dict,
                "test_results": {"findings_count": report_dict["findings_count"]},
            }

        def validate_markdown_handler(
            task: Task, config: KanomanConfig, registry: ProjectRegistry
        ) -> Dict[str, Any]:
            from pathlib import Path
            from kanoman.analysis.markdown_validator import MarkdownValidator

            validator = MarkdownValidator(workspace_root=config.workspace_root)
            raw_target = task.metadata.get("target_path") if task.metadata else None
            target = Path(raw_target) if raw_target else config.workspace_root
            if not target.is_absolute():
                target = (config.workspace_root / target).resolve()

            if target.is_file():
                findings = validator.validate_file(target)
                report_dict = {
                    "analyzer": "MarkdownValidator",
                    "files_scanned": 1,
                    "findings_count": len(findings),
                    "findings": [f.model_dump() for f in findings],
                }
            else:
                report = validator.validate_directory(target)
                report_dict = {
                    "analyzer": report.analyzer_name,
                    "files_scanned": report.files_scanned,
                    "findings_count": len(report.findings),
                    "summary_by_severity": report.summary_by_severity,
                    "findings": [f.model_dump() for f in report.findings],
                }

            msg = (
                f"Markdown validation completed: {report_dict['files_scanned']} file(s) scanned, "
                f"{report_dict['findings_count']} finding(s)."
            )
            return {
                "message": msg,
                "report": report_dict,
                "test_results": {"findings_count": report_dict["findings_count"]},
            }

        self.register_handler("ping", ping_handler)
        self.register_handler("inspect_workspace", inspect_workspace_handler)
        self.register_handler("analyze_python", analyze_python_handler)
        self.register_handler("validate_markdown", validate_markdown_handler)

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        """Register a custom task handler."""
        self._handlers[task_type.lower()] = handler

    def execute_task(self, task: Task, task_type: str = "ping") -> Task:
        """Execute task through the orchestrator pipeline with deterministic checkpoints."""
        clean_type = task_type.strip().lower()
        logger.info(
            f"Receiving task: {task.title} (type: {clean_type})",
            task_id=task.task_id,
            project_id=task.project_id,
            status="TASK_RECEIVED",
        )

        # Step 0: Ensure task is not in a terminal state
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise ValueError(f"Cannot execute task already in terminal state: {task.status.value}")

        # Step 1: Validate handler availability
        if clean_type not in self._handlers:
            err_msg = f"Unsupported task type '{clean_type}'. Supported: {list(self._handlers.keys())}"
            task.transition_to(TaskStatus.RUNNING)
            task.transition_to(TaskStatus.FAILED, error=err_msg)
            task.result_summary = err_msg
            logger.error(err_msg, task_id=task.task_id, status="UNSUPPORTED_TASK")
            return task

        # Step 2: Transition to RUNNING
        if task.status == TaskStatus.PENDING:
            task.transition_to(TaskStatus.RUNNING)

        handler = self._handlers[clean_type]

        # Step 3: Execute handler
        try:
            result = handler(task, self.config, self.registry)
            summary = str(result.get("message", "Task completed successfully."))
            task.result_summary = summary

            # Step 4: Create Checkpoint
            checkpoint = Checkpoint(
                task_id=task.task_id,
                project_id=task.project_id,
                status=TaskStatus.COMPLETED.value,
                change_summary=summary,
                test_results=result.get("test_results"),
                next_steps=result.get("next_steps", []),
            )
            self.recovery.save_checkpoint(checkpoint)
            task.checkpoint_id = checkpoint.checkpoint_id

            # Step 5: Transition to COMPLETED
            task.transition_to(TaskStatus.COMPLETED)
            logger.info(
                f"Task completed successfully: {task.task_id}",
                task_id=task.task_id,
                project_id=task.project_id,
                status="TASK_COMPLETED",
            )
        except Exception as exc:
            err_details = f"{exc.__class__.__name__}: {str(exc)}"
            task.transition_to(TaskStatus.FAILED, error=err_details)
            task.result_summary = f"Execution failed: {err_details}"

            # Create failure checkpoint
            chk_fail = Checkpoint(
                task_id=task.task_id,
                project_id=task.project_id,
                status=TaskStatus.FAILED.value,
                change_summary=f"Task failed: {err_details}",
                next_steps=["Inspect logs", "Check input parameters and retry"],
            )
            self.recovery.save_checkpoint(chk_fail)
            task.checkpoint_id = chk_fail.checkpoint_id

            logger.error(
                f"Task execution failed: {err_details}",
                task_id=task.task_id,
                project_id=task.project_id,
                status="TASK_FAILED",
                extra={"traceback": traceback.format_exc()},
            )

        return task
