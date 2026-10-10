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
from kanoman.logging.logger import get_logger, redact_sensitive_text

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

    def resolve_project_context(
        self,
        task: Task,
    ) -> tuple[Path, Optional[str], Optional[list[str]], bool]:
        """Resolve workspace root, allowed remote, allowed branches, and dry-run policy for a task.

        Fail-closed: If task specifies project_id, it must exist in self.registry.
        If project_id is not specified (None or empty), falls back to global Kanoman configuration.
        """
        if task.project_id:
            proj = self.registry.get_project(task.project_id)
            if not proj:
                raise ValueError(
                    f"Project '{task.project_id}' not found in registry. Fail-closed: refusing execution."
                )
            return (
                proj.workspace_root.resolve(),
                proj.allowed_remote_url,
                [proj.policy_branch],
                proj.git_dry_run_policy,
            )
        return (
            self.config.workspace_root.resolve(),
            self.config.git_allowed_remote,
            self.config.git_allowed_branches,
            self.config.git_dry_run,
        )

    def _register_default_handlers(self) -> None:
        """Register built-in safe task handlers."""

        def ping_handler(task: Task, config: KanomanConfig, registry: ProjectRegistry) -> Dict[str, Any]:
            ws_root, _, _, _ = self.resolve_project_context(task)
            return {
                "message": "Kanoman Core alive and operational.",
                "env": config.env.value,
                "workspace": str(ws_root),
                "project_id": task.project_id,
            }

        def inspect_workspace_handler(
            task: Task, config: KanomanConfig, registry: ProjectRegistry
        ) -> Dict[str, Any]:
            ws_root, _, _, _ = self.resolve_project_context(task)
            exists = ws_root.is_dir()
            return {
                "workspace_root": str(ws_root),
                "is_dir": exists,
                "project_count": len(registry.list_projects()),
                "project_id": task.project_id,
            }

        def analyze_python_handler(
            task: Task, config: KanomanConfig, registry: ProjectRegistry
        ) -> Dict[str, Any]:
            from pathlib import Path
            from kanoman.analysis.python_analyzer import PythonASTAnalyzer

            ws_root, _, _, _ = self.resolve_project_context(task)
            analyzer = PythonASTAnalyzer(workspace_root=ws_root)
            raw_target = task.metadata.get("target_path") if task.metadata else None
            target = Path(raw_target) if raw_target else ws_root
            if not target.is_absolute():
                target = (ws_root / target).resolve()

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

            ws_root, _, _, _ = self.resolve_project_context(task)
            validator = MarkdownValidator(workspace_root=ws_root)
            raw_target = task.metadata.get("target_path") if task.metadata else None
            target = Path(raw_target) if raw_target else ws_root
            if not target.is_absolute():
                target = (ws_root / target).resolve()

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

        def coordinate_agents_handler(
            task: Task, config: KanomanConfig, registry: ProjectRegistry
        ) -> Dict[str, Any]:
            from kanoman.agents.coordinator import MultiAgentCoordinator, CoordinatorStatus
            from kanoman.agents.models import AgentPlan, AgentPlanStep, AgentRole
            from kanoman.agents.quality_gate import AgentQualityGate
            from kanoman.agents.runners import (
                ArchitectRunner,
                CoderRunner,
                SecurityAuditorRunner,
                QAEngineerRunner,
                execute_end_to_end_specialist_workflow,
            )
            from kanoman.ai.mock import MockAIProvider
            from kanoman.git.controller import GitController

            ws_root, allowed_remote, allowed_branches, dry_run = self.resolve_project_context(task)

            # Wire GitController if permitted remote is configured for this project
            git_ctrl = None
            if allowed_remote:
                try:
                    git_ctrl = GitController(
                        workspace_root=ws_root,
                        allowed_remote=allowed_remote,
                        allowed_branches=allowed_branches,
                        config=config,
                    )
                except Exception:
                    pass

            quality_gate = AgentQualityGate(workspace_root=ws_root)
            coordinator = MultiAgentCoordinator(
                config=config,
                recovery_engine=self.recovery,
                git_controller=git_ctrl,
                quality_gate=quality_gate,
            )

            use_specialists = bool(task.metadata.get("use_specialists", False)) if task.metadata else False

            if use_specialists:
                # Resolve provider
                provider = None
                if task.metadata and "ai_provider" in task.metadata:
                    provider = task.metadata["ai_provider"]
                else:
                    prov_name = (
                        task.metadata.get("provider", config.default_ai_provider)
                        if task.metadata
                        else config.default_ai_provider
                    )
                    if prov_name == "mock":
                        provider = MockAIProvider()
                    else:
                        from kanoman.ai.router import AIRouter

                        router = AIRouter(config=config)
                        provider = router.get_provider(prov_name) or MockAIProvider()

                architect = ArchitectRunner(provider)
                coder = CoderRunner(provider)
                auditor = SecurityAuditorRunner(provider)
                qa = QAEngineerRunner(provider)

                result = execute_end_to_end_specialist_workflow(
                    task=task,
                    coordinator=coordinator,
                    architect=architect,
                    coder=coder,
                    auditor=auditor,
                    qa=qa,
                    quality_gate=quality_gate,
                )
            else:
                # Build or retrieve plan
                plan_data = task.metadata.get("plan") if task.metadata else None
                if plan_data and isinstance(plan_data, dict):
                    plan = AgentPlan.model_validate(plan_data)
                elif plan_data and isinstance(plan_data, AgentPlan):
                    plan = plan_data
                else:
                    step_arch = AgentPlanStep(
                        step_id="step_arch",
                        assigned_role=AgentRole.ARCHITECT,
                        title="Architecture Review",
                        description=task.description,
                    )
                    plan = AgentPlan(
                        task_id=task.task_id,
                        goal=task.title,
                        steps=[step_arch],
                        max_iterations=5,
                    )

                result = coordinator.execute_plan(task, plan)

            # Map coordinator status to task result
            if result.status == CoordinatorStatus.COMPLETED:
                msg = (
                    f"Multi-agent coordination completed successfully: "
                    f"{len(result.decisions)} decision(s) recorded."
                )
                return {
                    "message": msg,
                    "coordinator_result": result.model_dump(),
                    "test_results": {
                        "status": result.status.value,
                        "decisions_count": len(result.decisions),
                        "iterations": result.iterations,
                    },
                }
            elif result.status == CoordinatorStatus.REJECTED:
                err_msg = result.error or "Proposal rejected by security or quality review."
                raise ValueError(f"Multi-agent coordination rejected: {err_msg}")
            elif result.status == CoordinatorStatus.ABORTED:
                err_msg = result.error or "Coordination aborted by security veto."
                raise ValueError(f"Multi-agent coordination aborted (security veto): {err_msg}")
            elif result.status == CoordinatorStatus.TIMEOUT:
                raise TimeoutError(f"Multi-agent coordination timed out: {result.error}")
            elif result.status == CoordinatorStatus.CYCLE_DETECTED:
                raise RuntimeError(f"Multi-agent coordination cycle detected: {result.error}")
            else:
                raise RuntimeError(f"Multi-agent coordination failed: {result.error}")

        self.register_handler("ping", ping_handler)
        self.register_handler("inspect_workspace", inspect_workspace_handler)
        self.register_handler("analyze_python", analyze_python_handler)
        self.register_handler("validate_markdown", validate_markdown_handler)
        self.register_handler("coordinate_agents", coordinate_agents_handler)
        self.register_handler("multi_agent", coordinate_agents_handler)

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
            raw_err = f"{exc.__class__.__name__}: {str(exc)}"
            err_details = redact_sensitive_text(raw_err)
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
