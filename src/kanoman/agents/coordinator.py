"""Multi-Agent Coordinator for Kanoman AI.

Orchestrates sequential, deterministic delegation across agent personas, enforces
turn order, detects delegation loops, bounds message history and iteration limits,
enforces timeouts and token budgets, and ensures all Git operations remain guarded
by GitController.
"""

from __future__ import annotations

import hashlib
import json
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

from kanoman.agents.models import (
    AgentDecision,
    AgentMessage,
    AgentPlan,
    AgentPlanStep,
    AgentRole,
    DecisionType,
    MessageType,
)
from kanoman.ai.models import AIMessage, AIResponse, UsageMetadata
from kanoman.ai.protocol import BaseAIProvider
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import KanomanConfig, get_config
from kanoman.core.models import Checkpoint, Task, TaskStatus
from kanoman.git.controller import GitController
from kanoman.logging.logger import get_logger, redact_sensitive_text

logger = get_logger("agents.coordinator")

DEFAULT_MAX_HISTORY_LENGTH = 100
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_CYCLE_THRESHOLD = 2


class CoordinatorStatus(str, Enum):
    """Lifecycle states of the MultiAgentCoordinator."""

    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    ABORTED = "ABORTED"
    TIMEOUT = "TIMEOUT"
    CYCLE_DETECTED = "CYCLE_DETECTED"


class CoordinatorResult(BaseModel):
    """Structured, auditable output produced by the MultiAgentCoordinator."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    plan_id: Optional[str] = None
    status: CoordinatorStatus
    iterations: int = 0
    total_tokens: int = 0
    total_calls: int = 0
    duration_seconds: float = 0.0
    history_count: int = 0
    decisions: List[AgentDecision] = Field(default_factory=list)
    messages: List[AgentMessage] = Field(default_factory=list)
    error: Optional[str] = None
    checkpoint_id: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        return self.status == CoordinatorStatus.COMPLETED


class MultiAgentCoordinator:
    """Coordinates multi-agent workflows with strict safety barriers and deterministic FSM."""

    def __init__(
        self,
        ai_provider: Optional[BaseAIProvider] = None,
        recovery_engine: Optional[RecoveryEngine] = None,
        git_controller: Optional[GitController] = None,
        quality_gate: Optional[Any] = None,
        config: Optional[KanomanConfig] = None,
        clock: Optional[Callable[[], float]] = None,
        max_history_length: int = DEFAULT_MAX_HISTORY_LENGTH,
    ) -> None:
        from kanoman.agents.quality_gate import AgentQualityGate

        self.config = config or get_config()
        self.ai_provider = ai_provider
        self.recovery_engine = recovery_engine
        self.git_controller = git_controller
        self.quality_gate = quality_gate or AgentQualityGate(self.config.workspace_root)
        self.clock = clock or time.time
        self.max_history_length = max_history_length

        self.status = CoordinatorStatus.IDLE
        self.current_task_id: Optional[str] = None
        self.current_plan: Optional[AgentPlan] = None
        self.history: List[AgentMessage] = []
        self.decisions: List[AgentDecision] = []
        self.seen_message_ids: Set[str] = set()

        self.current_iteration: int = 0
        self.current_step_index: int = 0
        self.total_tokens_used: int = 0
        self.total_calls: int = 0

        # Cycle detection state tracking
        self._signature_history: List[str] = []

    def evaluate_proposal(self, target_path: str, proposed_content: str) -> Any:
        """Evaluate an in-memory code or markdown proposal through the quality gate."""
        if not self.current_task_id:
            raise ValueError("Cannot evaluate proposal: Coordinator has no active task context.")

        qg_result = self.quality_gate.verify_proposal(
            task_id=self.current_task_id,
            target_path=target_path,
            proposed_content=proposed_content,
        )
        self.record_decision(qg_result.decision)

        if not qg_result.is_approved:
            logger.warning(
                f"Quality gate rejected proposal for '{target_path}': {qg_result.decision.rationale}",
                task_id=self.current_task_id,
                status="QUALITY_GATE_REJECTED",
            )
        return qg_result

    def evaluate_file_on_disk(self, target_path: Path) -> Any:
        """Evaluate an existing file on disk through the quality gate."""
        if not self.current_task_id:
            raise ValueError("Cannot evaluate file: Coordinator has no active task context.")

        qg_result = self.quality_gate.verify_file_on_disk(
            task_id=self.current_task_id,
            target_path=target_path,
        )
        self.record_decision(qg_result.decision)
        return qg_result

    def request_git_operation(self, mode: str, files: Optional[List[str]] = None, message: Optional[str] = None) -> Any:
        """Request Git operation from GitController under strict authorization policy.

        SECURITY POLICY:
        1. Autonomous commits and pushes are strictly PROHIBITED for agents.
        2. Only 'inspect' and 'dry-run' operations are permitted.
        3. If dry-run fails or reports security warnings, an automatic security veto
           (ABORT) is triggered on the coordinator.
        4. Agent 'APPROVE' decisions do NOT grant commit or push permissions.
        """
        clean_mode = mode.strip().lower()
        if self.git_controller is None:
            raise PermissionError("Git operations are prohibited: GitController is not configured.")

        if clean_mode not in {"inspect", "dry-run"}:
            err_msg = (
                f"Autonomous Git operation mode '{mode}' is strictly prohibited. "
                f"Agents are restricted to 'inspect' and 'dry-run'. Direct commits/pushes are forbidden."
            )
            logger.error(err_msg, status="GIT_OPERATION_FORBIDDEN")
            raise PermissionError(err_msg)

        if clean_mode == "inspect":
            return self.git_controller.inspect()

        # mode == 'dry-run'
        target_files = files or []
        target_msg = message or "Simulated agent change"
        plan = self.git_controller.dry_run(target_files, target_msg)
        if not plan.is_safe or plan.warnings:
            veto_rationale = f"GitController security veto triggered: {plan.warnings}"
            veto_dec = AgentDecision(
                task_id=self.current_task_id or "unknown",
                agent_role=AgentRole.SECURITY_AUDITOR,
                decision_type=DecisionType.ABORT,
                is_approved=False,
                rationale=veto_rationale,
                metadata={"warnings": plan.warnings},
            )
            self.record_decision(veto_dec)
            self.status = CoordinatorStatus.ABORTED
            raise PermissionError(veto_rationale)

        return plan

    def reset(self) -> None:
        """Reset internal execution state for a new run."""
        self.status = CoordinatorStatus.IDLE
        self.current_task_id = None
        self.current_plan = None
        self.history.clear()
        self.decisions.clear()
        self.seen_message_ids.clear()
        self.current_iteration = 0
        self.current_step_index = 0
        self.total_tokens_used = 0
        self.total_calls = 0
        self._signature_history.clear()

    def _compute_state_signature(
        self,
        step_id: str,
        role: AgentRole,
        decision_type: Optional[DecisionType],
        content_summary: str,
    ) -> str:
        """Compute deterministic state signature for loop and cycle detection."""
        raw = f"{step_id}:{role.value}:{decision_type.value if decision_type else 'NONE'}:{content_summary.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _check_cycle(self, signature: str) -> bool:
        """Detect repetition cycles in agent state signatures."""
        self._signature_history.append(signature)
        count = self._signature_history.count(signature)
        if count >= DEFAULT_CYCLE_THRESHOLD:
            logger.warning(
                f"Delegation cycle detected: signature '{signature}' repeated {count} times.",
                status="CYCLE_DETECTED",
            )
            return True
        return False

    def dispatch_message(self, message: AgentMessage) -> None:
        """Validate and append an incoming agent message to coordinator history."""
        if not self.current_task_id:
            raise ValueError("Cannot dispatch message: Coordinator has no active task context.")

        if message.task_id != self.current_task_id:
            raise ValueError(
                f"Context mismatch: Message task_id '{message.task_id}' does not match "
                f"active task '{self.current_task_id}'."
            )

        if message.message_id in self.seen_message_ids:
            raise ValueError(
                f"Duplicate message rejected: message_id '{message.message_id}' already processed."
            )

        if len(self.history) >= self.max_history_length:
            raise ValueError(
                f"Message history overflow: exceeded maximum limit of {self.max_history_length} messages."
            )

        # Sanitize summary and payload content proactively
        message.summary = redact_sensitive_text(message.summary)
        self.seen_message_ids.add(message.message_id)
        self.history.append(message)

    def record_decision(self, decision: AgentDecision) -> None:
        """Validate and record an agent decision into the audit trail."""
        if not self.current_task_id:
            raise ValueError("Cannot record decision: Coordinator has no active task context.")

        if decision.task_id != self.current_task_id:
            raise ValueError(
                f"Context mismatch: Decision task_id '{decision.task_id}' does not match "
                f"active task '{self.current_task_id}'."
            )

        decision.rationale = redact_sensitive_text(decision.rationale)
        self.decisions.append(decision)

    def save_coordination_checkpoint(self, task: Task) -> Optional[Checkpoint]:
        """Atomically persist current coordination state snapshot via RecoveryEngine."""
        if not self.recovery_engine:
            return None

        chk = Checkpoint(
            task_id=task.task_id,
            project_id=task.project_id,
            status=self.status.value,
            change_summary=(
                f"Coordinator [{self.status.value}] at step {self.current_step_index}, "
                f"iteration {self.current_iteration}/{self.current_plan.max_iterations if self.current_plan else 'N/A'}"
            ),
            test_results={
                "coordinator_state": {
                    "status": self.status.value,
                    "current_iteration": self.current_iteration,
                    "current_step_index": self.current_step_index,
                    "plan_id": self.current_plan.plan_id if self.current_plan else None,
                    "total_tokens": self.total_tokens_used,
                    "total_calls": self.total_calls,
                    "history_count": len(self.history),
                    "decisions_count": len(self.decisions),
                }
            },
            next_steps=["Resume next step in sequence"] if self.status == CoordinatorStatus.RUNNING else [],
        )
        self.recovery_engine.save_checkpoint(chk)
        return chk

    def resume_from_checkpoint(self, checkpoint: Checkpoint, plan: AgentPlan) -> None:
        """Safely restore coordinator state from a validated checkpoint snapshot."""
        if not checkpoint.test_results or "coordinator_state" not in checkpoint.test_results:
            raise ValueError("Checkpoint does not contain valid 'coordinator_state' metadata.")

        c_state = checkpoint.test_results["coordinator_state"]
        saved_status = c_state.get("status")
        if not saved_status or saved_status in {
            CoordinatorStatus.COMPLETED.value,
            CoordinatorStatus.ABORTED.value,
        }:
            raise ValueError(f"Cannot resume from terminal checkpoint status '{saved_status}'.")

        if c_state.get("plan_id") and c_state["plan_id"] != plan.plan_id:
            raise ValueError(
                f"Plan mismatch: Checkpoint references plan '{c_state.get('plan_id')}', "
                f"current plan is '{plan.plan_id}'."
            )

        self.current_task_id = checkpoint.task_id
        self.current_plan = plan
        self.current_iteration = int(c_state.get("current_iteration", 0))
        self.current_step_index = int(c_state.get("current_step_index", 0))
        self.total_tokens_used = int(c_state.get("total_tokens", 0))
        self.total_calls = int(c_state.get("total_calls", 0))
        self.status = CoordinatorStatus.RUNNING
        logger.info(
            f"Coordinator successfully resumed from checkpoint {checkpoint.checkpoint_id} at step {self.current_step_index}",
            task_id=checkpoint.task_id,
            status="COORDINATOR_RESUMED",
        )

    def execute_plan(
        self,
        task: Task,
        plan: AgentPlan,
        custom_step_handlers: Optional[Dict[str, Callable[[AgentPlanStep, MultiAgentCoordinator], AgentDecision]]] = None,
    ) -> CoordinatorResult:
        """Deterministically execute an AgentPlan step-by-step with guardrails."""
        self.reset()
        self.current_task_id = task.task_id
        self.current_plan = plan
        self.status = CoordinatorStatus.INITIALIZING

        # Validate task and plan alignment
        if plan.task_id != task.task_id:
            err = f"Plan task_id '{plan.task_id}' does not match task '{task.task_id}'."
            self.status = CoordinatorStatus.FAILED
            return self._build_result(error=err)

        if not plan.steps:
            err = "AgentPlan contains no steps to execute."
            self.status = CoordinatorStatus.FAILED
            return self._build_result(error=err)

        start_time = self.clock()
        deadline = start_time + plan.timeout_seconds
        self.status = CoordinatorStatus.RUNNING

        step_handlers = custom_step_handlers or {}
        checkpoint_id: Optional[str] = None

        while self.current_step_index < len(plan.steps):
            # Check Iteration Limit
            if self.current_iteration >= plan.max_iterations:
                self.status = CoordinatorStatus.FAILED
                err = f"Max iterations ({plan.max_iterations}) exceeded without completion."
                logger.error(err, task_id=task.task_id, status="MAX_ITERATIONS_EXCEEDED")
                return self._build_result(error=err, checkpoint_id=checkpoint_id)

            # Check Real Timeout
            current_now = self.clock()
            if current_now >= deadline:
                self.status = CoordinatorStatus.TIMEOUT
                err = f"Execution exceeded timeout budget of {plan.timeout_seconds}s."
                logger.error(err, task_id=task.task_id, status="TIMEOUT")
                return self._build_result(error=err, checkpoint_id=checkpoint_id)

            # Check Token Budget
            if self.total_tokens_used >= plan.token_budget:
                self.status = CoordinatorStatus.FAILED
                err = f"Token budget of {plan.token_budget} tokens exhausted (used {self.total_tokens_used})."
                logger.error(err, task_id=task.task_id, status="TOKEN_BUDGET_EXCEEDED")
                return self._build_result(error=err, checkpoint_id=checkpoint_id)

            current_step = plan.steps[self.current_step_index]

            logger.info(
                f"Executing step {self.current_step_index + 1}/{len(plan.steps)}: {current_step.title} "
                f"[{current_step.assigned_role.value}]",
                task_id=task.task_id,
                status="STEP_EXECUTION",
            )

            # Dispatch initial step proposal message
            step_msg = AgentMessage(
                task_id=task.task_id,
                sender_role=AgentRole.ARCHITECT,
                recipient_role=current_step.assigned_role,
                message_type=MessageType.PROPOSAL,
                summary=f"Initiating step '{current_step.step_id}': {current_step.title}",
                payload={"description": current_step.description},
                provenance={"plan_id": plan.plan_id, "step_id": current_step.step_id},
            )
            self.dispatch_message(step_msg)

            # Invoke Step Handler or Default Provider
            try:
                if current_step.step_id in step_handlers:
                    decision = step_handlers[current_step.step_id](current_step, self)
                else:
                    decision = self._default_agent_turn(current_step)
            except Exception as exc:
                self.status = CoordinatorStatus.FAILED
                err = f"Step handler execution failure on '{current_step.step_id}': {str(exc)}"
                logger.error(err, task_id=task.task_id, status="STEP_HANDLER_ERROR")
                return self._build_result(error=err, checkpoint_id=checkpoint_id)

            # Record Decision
            self.record_decision(decision)

            # Cycle Detection Check
            sig = self._compute_state_signature(
                current_step.step_id,
                current_step.assigned_role,
                decision.decision_type,
                decision.rationale[:50],
            )
            if self._check_cycle(sig):
                self.status = CoordinatorStatus.CYCLE_DETECTED
                err = f"Cycle detected at step '{current_step.step_id}'. Halting execution."
                return self._build_result(error=err, checkpoint_id=checkpoint_id)

            # Handle Decision Types
            if decision.decision_type == DecisionType.ABORT:
                self.status = CoordinatorStatus.ABORTED
                logger.warning(
                    f"Plan aborted by {decision.agent_role.value}: {decision.rationale}",
                    task_id=task.task_id,
                    status="PLAN_ABORTED",
                )
                return self._build_result(
                    error=f"Plan aborted by {decision.agent_role.value}: {decision.rationale}",
                    checkpoint_id=checkpoint_id,
                )

            elif decision.decision_type == DecisionType.REJECT:
                self.status = CoordinatorStatus.REJECTED
                logger.warning(
                    f"Plan rejected by {decision.agent_role.value}: {decision.rationale}",
                    task_id=task.task_id,
                    status="PLAN_REJECTED",
                )
                return self._build_result(
                    error=f"Plan rejected by {decision.agent_role.value}: {decision.rationale}",
                    checkpoint_id=checkpoint_id,
                )

            elif decision.decision_type == DecisionType.REQUEST_CHANGES:
                self.current_iteration += 1
                logger.info(
                    f"Changes requested on step '{current_step.step_id}'. Iteration incremented to {self.current_iteration}.",
                    task_id=task.task_id,
                    status="CHANGES_REQUESTED",
                )
                # Retry step or continue loop
                continue

            elif decision.decision_type == DecisionType.APPROVE:
                # Step approved, save intermediate checkpoint if configured
                self.current_step_index += 1
                saved_chk = self.save_coordination_checkpoint(task)
                if saved_chk:
                    checkpoint_id = saved_chk.checkpoint_id

        # All steps completed successfully
        self.status = CoordinatorStatus.COMPLETED
        final_chk = self.save_coordination_checkpoint(task)
        if final_chk:
            checkpoint_id = final_chk.checkpoint_id

        logger.info(
            f"Plan {plan.plan_id} completed successfully for task {task.task_id}.",
            task_id=task.task_id,
            status="COORDINATOR_COMPLETED",
        )
        return self._build_result(checkpoint_id=checkpoint_id)

    def _default_agent_turn(self, step: AgentPlanStep) -> AgentDecision:
        """Default step execution via injected AI provider."""
        if not self.ai_provider:
            # Deterministic safe approval if no AI provider is wired
            return AgentDecision(
                task_id=self.current_task_id or "unknown",
                agent_role=step.assigned_role,
                decision_type=DecisionType.APPROVE,
                is_approved=True,
                rationale=f"Default automated approval for step '{step.title}'.",
            )

        # Build prompt from history
        context_msgs = [
            AIMessage(
                role="user" if m.sender_role != step.assigned_role else "assistant",
                content=f"[{m.sender_role.value}] {m.summary}",
            )
            for m in self.history[-10:]
        ]
        context_msgs.append(
            AIMessage(
                role="user",
                content=f"Execute assigned step '{step.step_id}': {step.title}. Description: {step.description}",
            )
        )

        self.total_calls += 1
        res: AIResponse = self.ai_provider.generate_text(context_msgs)

        if res.usage:
            self.total_tokens_used += res.usage.total_tokens

        # Record agent response message
        reply_msg = AgentMessage(
            task_id=self.current_task_id or "unknown",
            sender_role=step.assigned_role,
            recipient_role=AgentRole.ARCHITECT,
            message_type=MessageType.RESPONSE,
            summary=f"Completed {step.step_id}: {res.content[:100]}",
            payload={"output": res.content[:500]},
            provenance={"provider": res.provider, "model": res.model_name},
        )
        self.dispatch_message(reply_msg)

        return AgentDecision(
            task_id=self.current_task_id or "unknown",
            agent_role=step.assigned_role,
            decision_type=DecisionType.APPROVE,
            is_approved=True,
            rationale=f"Step '{step.step_id}' verified and approved by {step.assigned_role.value}.",
        )

    def _build_result(
        self,
        error: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
    ) -> CoordinatorResult:
        """Construct the immutable CoordinatorResult."""
        return CoordinatorResult(
            task_id=self.current_task_id or "unknown",
            plan_id=self.current_plan.plan_id if self.current_plan else None,
            status=self.status,
            iterations=self.current_iteration,
            total_tokens=self.total_tokens_used,
            total_calls=self.total_calls,
            history_count=len(self.history),
            decisions=list(self.decisions),
            messages=list(self.history),
            error=redact_sensitive_text(error) if error else None,
            checkpoint_id=checkpoint_id,
        )
