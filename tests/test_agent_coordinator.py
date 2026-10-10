"""Unit and integration tests for MultiAgentCoordinator, delegation FSM, and cycle safety."""

from pathlib import Path
from typing import List
import pytest

from kanoman.agents.coordinator import (
    CoordinatorResult,
    CoordinatorStatus,
    MultiAgentCoordinator,
)
from kanoman.agents.models import (
    AgentDecision,
    AgentMessage,
    AgentPlan,
    AgentPlanStep,
    AgentRole,
    DecisionType,
    MessageType,
)
from kanoman.ai.mock import MockAIProvider
from kanoman.ai.models import AIErrorType
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.core.models import Checkpoint, Task, TaskPriority, TaskStatus
from kanoman.git.controller import GitController


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def recovery_engine(temp_workspace: Path) -> RecoveryEngine:
    return RecoveryEngine(checkpoint_dir=temp_workspace / ".kanoman_checkpoints")


@pytest.fixture
def sample_task() -> Task:
    return Task(
        task_id="task_coord_001",
        title="Develop Secure Auth Module",
        description="Implement JWT authentication with secret validation",
        priority=TaskPriority.HIGH,
    )


@pytest.fixture
def sample_plan(sample_task: Task) -> AgentPlan:
    step1 = AgentPlanStep(
        step_id="step_arch",
        assigned_role=AgentRole.ARCHITECT,
        title="Design Architecture",
        description="Specify token format and claims validation",
    )
    step2 = AgentPlanStep(
        step_id="step_code",
        assigned_role=AgentRole.CODER,
        title="Implement Auth Logic",
        description="Code the token generator and validator functions",
        dependencies=["step_arch"],
    )
    step3 = AgentPlanStep(
        step_id="step_qa",
        assigned_role=AgentRole.QA_ENGINEER,
        title="Verify Test Suite",
        description="Run test suite to verify token expiration handling",
        dependencies=["step_code"],
    )
    return AgentPlan(
        task_id=sample_task.task_id,
        goal="Complete authentication service",
        steps=[step1, step2, step3],
        max_iterations=3,
        token_budget=10000,
        timeout_seconds=30,
    )


# =====================================================================
# 1. Successful Delegation Flow & Turn Order
# =====================================================================

def test_coordinator_successful_delegation_flow(
    sample_task: Task, sample_plan: AgentPlan, recovery_engine: RecoveryEngine
):
    provider = MockAIProvider(default_reply="Task completed and verified cleanly.")
    coordinator = MultiAgentCoordinator(ai_provider=provider, recovery_engine=recovery_engine)

    result = coordinator.execute_plan(sample_task, sample_plan)

    assert result.is_successful is True
    assert result.status == CoordinatorStatus.COMPLETED
    assert result.task_id == sample_task.task_id
    assert result.plan_id == sample_plan.plan_id
    assert len(result.decisions) == 3
    assert result.checkpoint_id is not None
    assert provider.call_count == 3


def test_coordinator_agent_turn_order(sample_task: Task, sample_plan: AgentPlan):
    roles_executed: List[AgentRole] = []

    def tracking_handler(step: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
        roles_executed.append(step.assigned_role)
        return AgentDecision(
            task_id=sample_task.task_id,
            agent_role=step.assigned_role,
            decision_type=DecisionType.APPROVE,
            is_approved=True,
            rationale=f"Step {step.step_id} approved.",
        )

    handlers = {
        "step_arch": tracking_handler,
        "step_code": tracking_handler,
        "step_qa": tracking_handler,
    }

    coordinator = MultiAgentCoordinator()
    result = coordinator.execute_plan(sample_task, sample_plan, custom_step_handlers=handlers)

    assert result.status == CoordinatorStatus.COMPLETED
    assert roles_executed == [
        AgentRole.ARCHITECT,
        AgentRole.CODER,
        AgentRole.QA_ENGINEER,
    ]


# =====================================================================
# 2. Safety Bounds: Max Iterations, Timeout, Token Budget
# =====================================================================

def test_coordinator_max_iterations_enforced(sample_task: Task, sample_plan: AgentPlan):
    # Handler continually requests changes
    def infinite_loop_handler(step: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
        return AgentDecision(
            task_id=sample_task.task_id,
            agent_role=step.assigned_role,
            decision_type=DecisionType.REQUEST_CHANGES,
            is_approved=False,
            rationale=f"Revision requested at count {coord.current_iteration}",
        )

    sample_plan.max_iterations = 2
    coordinator = MultiAgentCoordinator()
    result = coordinator.execute_plan(
        sample_task, sample_plan, custom_step_handlers={"step_arch": infinite_loop_handler}
    )

    assert result.status == CoordinatorStatus.FAILED
    assert "Max iterations" in (result.error or "")
    assert result.iterations >= 2


def test_coordinator_timeout_enforced(sample_task: Task, sample_plan: AgentPlan):
    # Simulated clock that jumps beyond timeout deadline
    time_cursor = [1000.0]

    def mock_clock() -> float:
        # Each call advances time by 20 seconds
        val = time_cursor[0]
        time_cursor[0] += 20.0
        return val

    sample_plan.timeout_seconds = 15  # Deadline is start (1000) + 15 = 1015
    coordinator = MultiAgentCoordinator(clock=mock_clock)

    result = coordinator.execute_plan(sample_task, sample_plan)

    assert result.status == CoordinatorStatus.TIMEOUT
    assert "timeout budget" in (result.error or "")


def test_coordinator_token_budget_enforced(sample_task: Task, sample_plan: AgentPlan):
    provider = MockAIProvider()
    # Artificially small budget
    sample_plan.token_budget = 40
    coordinator = MultiAgentCoordinator(ai_provider=provider)

    result = coordinator.execute_plan(sample_task, sample_plan)

    # First call uses ~50 tokens in mock, exceeding 40 on step 2
    assert result.status == CoordinatorStatus.FAILED
    assert "Token budget" in (result.error or "")


# =====================================================================
# 3. Cycle Detection (Anti-Looping)
# =====================================================================

def test_coordinator_cycle_detection(sample_task: Task, sample_plan: AgentPlan):
    # Handler returns identical decision rationale on every turn
    def repetitive_handler(step: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
        return AgentDecision(
            task_id=sample_task.task_id,
            agent_role=step.assigned_role,
            decision_type=DecisionType.REQUEST_CHANGES,
            is_approved=False,
            rationale="Exact same feedback without any progress made.",
        )

    coordinator = MultiAgentCoordinator()
    result = coordinator.execute_plan(
        sample_task, sample_plan, custom_step_handlers={"step_arch": repetitive_handler}
    )

    assert result.status == CoordinatorStatus.CYCLE_DETECTED
    assert "Cycle detected" in (result.error or "")


# =====================================================================
# 4. Message Validation, Duplicate & Context Mismatch
# =====================================================================

def test_coordinator_duplicate_and_context_mismatch(sample_task: Task):
    coordinator = MultiAgentCoordinator()
    coordinator.current_task_id = sample_task.task_id

    msg1 = AgentMessage(
        message_id="msg_fixed_123",
        task_id=sample_task.task_id,
        sender_role=AgentRole.ARCHITECT,
        summary="Message 1",
    )
    coordinator.dispatch_message(msg1)

    # Duplicate message ID rejected
    with pytest.raises(ValueError, match="Duplicate message rejected"):
        coordinator.dispatch_message(msg1)

    # Context mismatch rejected
    msg_other_task = AgentMessage(
        task_id="task_other_999",
        sender_role=AgentRole.CODER,
        summary="Message for wrong task",
    )
    with pytest.raises(ValueError, match="Context mismatch"):
        coordinator.dispatch_message(msg_other_task)


def test_coordinator_max_history_length_enforced(sample_task: Task):
    coordinator = MultiAgentCoordinator(max_history_length=3)
    coordinator.current_task_id = sample_task.task_id

    for i in range(3):
        msg = AgentMessage(
            task_id=sample_task.task_id,
            sender_role=AgentRole.ARCHITECT,
            summary=f"Summary {i}",
        )
        coordinator.dispatch_message(msg)

    # 4th message exceeds history length
    msg_overflow = AgentMessage(
        task_id=sample_task.task_id,
        sender_role=AgentRole.ARCHITECT,
        summary="Overflow message",
    )
    with pytest.raises(ValueError, match="Message history overflow"):
        coordinator.dispatch_message(msg_overflow)


# =====================================================================
# 5. Decision Handling: REJECT & ABORT
# =====================================================================

def test_coordinator_reject_decision_handled(sample_task: Task, sample_plan: AgentPlan):
    def reject_handler(step: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
        return AgentDecision(
            task_id=sample_task.task_id,
            agent_role=step.assigned_role,
            decision_type=DecisionType.REJECT,
            is_approved=False,
            rationale="Critical architectural flaws detected.",
        )

    coordinator = MultiAgentCoordinator()
    result = coordinator.execute_plan(
        sample_task, sample_plan, custom_step_handlers={"step_arch": reject_handler}
    )

    assert result.status == CoordinatorStatus.REJECTED
    assert "Critical architectural flaws" in (result.error or "")


def test_coordinator_abort_decision_handled(sample_task: Task, sample_plan: AgentPlan):
    def abort_handler(step: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
        return AgentDecision(
            task_id=sample_task.task_id,
            agent_role=step.assigned_role,
            decision_type=DecisionType.ABORT,
            is_approved=False,
            rationale="Security audit found high vulnerability.",
        )

    coordinator = MultiAgentCoordinator()
    result = coordinator.execute_plan(
        sample_task, sample_plan, custom_step_handlers={"step_arch": abort_handler}
    )

    assert result.status == CoordinatorStatus.ABORTED
    assert "Security audit found high vulnerability" in (result.error or "")


# =====================================================================
# 6. Provider Failure & Unhandled Error Handling
# =====================================================================

def test_coordinator_provider_failure_handled(sample_task: Task, sample_plan: AgentPlan):
    failing_provider = MockAIProvider(simulate_error=AIErrorType.SERVICE_UNAVAILABLE)
    coordinator = MultiAgentCoordinator(ai_provider=failing_provider)

    result = coordinator.execute_plan(sample_task, sample_plan)

    assert result.status == CoordinatorStatus.FAILED
    assert "SERVICE_UNAVAILABLE" in (result.error or "")


# =====================================================================
# 7. Checkpoint & Recovery Integration
# =====================================================================

def test_coordinator_resume_from_valid_checkpoint(
    sample_task: Task, sample_plan: AgentPlan, recovery_engine: RecoveryEngine
):
    coordinator = MultiAgentCoordinator(recovery_engine=recovery_engine)

    # Create synthetic intermediate checkpoint at step 1
    chk = Checkpoint(
        task_id=sample_task.task_id,
        status="RUNNING",
        change_summary="Intermediate checkpoint",
        test_results={
            "coordinator_state": {
                "status": "RUNNING",
                "current_iteration": 1,
                "current_step_index": 1,
                "plan_id": sample_plan.plan_id,
                "total_tokens": 150,
                "total_calls": 1,
                "history_count": 2,
            }
        },
    )
    recovery_engine.save_checkpoint(chk)

    # Resume coordinator from checkpoint
    coordinator.resume_from_checkpoint(chk, sample_plan)

    assert coordinator.status == CoordinatorStatus.RUNNING
    assert coordinator.current_step_index == 1
    assert coordinator.current_iteration == 1
    assert coordinator.total_tokens_used == 150


def test_coordinator_rejects_corrupted_checkpoint(
    sample_task: Task, sample_plan: AgentPlan, recovery_engine: RecoveryEngine
):
    coordinator = MultiAgentCoordinator(recovery_engine=recovery_engine)

    # Checkpoint without coordinator_state metadata
    chk_corrupt = Checkpoint(
        task_id=sample_task.task_id,
        status="RUNNING",
        change_summary="Corrupted without metadata",
        test_results={},
    )

    with pytest.raises(ValueError, match="does not contain valid 'coordinator_state'"):
        coordinator.resume_from_checkpoint(chk_corrupt, sample_plan)


# =====================================================================
# 8. Secret Sanitization on Messages and Errors
# =====================================================================

def test_coordinator_sanitizes_secrets(sample_task: Task, sample_plan: AgentPlan):
    leaked_token = "gh" + "p_" + ("a" * 25)

    def leaking_handler(step: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
        return AgentDecision(
            task_id=sample_task.task_id,
            agent_role=step.assigned_role,
            decision_type=DecisionType.REJECT,
            is_approved=False,
            rationale=f"Secret exposed in error: {leaked_token}",
        )

    coordinator = MultiAgentCoordinator()
    result = coordinator.execute_plan(
        sample_task, sample_plan, custom_step_handlers={"step_arch": leaking_handler}
    )

    assert leaked_token not in (result.error or "")
    assert "***REDACTED_SECRET***" in (result.error or "")


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Create a clean local git repository for testing coordinator git isolation."""
    import subprocess
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@kanoman.local"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/qomaruddindjamal/kanoman.git"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    return repo_dir


# =====================================================================
# 9. Git Isolation Enforcement
# =====================================================================

def test_coordinator_enforces_git_isolation(
    temp_git_repo: Path, sample_task: Task, sample_plan: AgentPlan
):
    # Verify coordinator never performs unilateral commits or pushes
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    coordinator = MultiAgentCoordinator(git_controller=ctrl)
    result = coordinator.execute_plan(sample_task, sample_plan)

    assert result.status == CoordinatorStatus.COMPLETED
    # Git status remains clean and unmutated
    git_status = ctrl.inspect()
    assert len(git_status.staged_files) == 0
    assert git_status.latest_commit_sha is None
