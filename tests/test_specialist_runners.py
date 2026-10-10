"""Comprehensive unit and integration tests for Specialist Runners and AIRouter integration.

Tests:
1. Runner initialization and role boundaries.
2. Architect plan generation (default fallback and custom structured steps).
3. Coder in-memory proposal generation (zero filesystem mutation).
4. CodeProposal Pydantic model validation and constraints.
5. Security Auditor approval of clean proposals.
6. Security Auditor automatic VETO when Quality Gate fails (hard invariant).
7. Security Auditor LLM rejection / abort.
8. QA Engineer evaluation and approval.
9. QA Engineer rejection when Security Auditor rejected.
10. QA Engineer change requests.
11. End-to-end specialist workflow: success path.
12. End-to-end specialist workflow: halting on AST security violation (eval/exec).
13. End-to-end specialist workflow: halting on syntax error.
14. End-to-end specialist workflow: zero filesystem writes invariant.
15. GitController veto invariant: agent APPROVE does not grant commit/push permissions.
16. Provider error handling fails closed.
17. Malformed / empty provider response handling.
18. Secret sanitization on error logging.
19. Correlation ID and audit trail consistency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest
from pydantic import ValidationError

from kanoman.agents.coordinator import CoordinatorResult, CoordinatorStatus, MultiAgentCoordinator
from kanoman.agents.models import (
    AgentDecision,
    AgentMessage,
    AgentPlan,
    AgentPlanStep,
    AgentRole,
    DecisionType,
    MessageType,
)
from kanoman.agents.quality_gate import AgentQualityGate, QualityGateResult
from kanoman.agents.runners import (
    ArchitectRunner,
    BaseSpecialistRunner,
    CoderRunner,
    CodeProposal,
    QAEngineerRunner,
    SecurityAuditorRunner,
    execute_end_to_end_specialist_workflow,
)
from kanoman.ai.models import (
    AIErrorType,
    AIException,
    AIMessage,
    AIProviderCapabilities,
    AIResponse,
    UsageMetadata,
)
from kanoman.ai.mock import MockAIProvider
from kanoman.core.models import Task, TaskPriority, TaskStatus
from kanoman.git.controller import GitController


class ConfigurableMockProvider(MockAIProvider):
    """Configurable mock provider returning custom structured data."""

    def __init__(
        self,
        structured_data: Optional[Dict[str, Any]] = None,
        raw_content: Optional[str] = None,
        simulate_error: Optional[AIErrorType] = None,
    ) -> None:
        super().__init__(name="configurable-mock", simulate_error=simulate_error)
        self._custom_structured_data = structured_data
        self._raw_content = raw_content

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        self.call_count += 1
        self.last_messages = messages
        self._maybe_raise()

        data = self._custom_structured_data
        content = self._raw_content if self._raw_content is not None else (json.dumps(data) if data is not None else "")

        return AIResponse(
            provider=self.provider_name,
            model_name="configurable-mock-v1",
            content=content,
            structured_data=data,
            usage=UsageMetadata(prompt_tokens=25, completion_tokens=35, total_tokens=60),
        )


@pytest.fixture
def sample_task() -> Task:
    return Task(
        task_id="task_specialist_001",
        title="Implement Secure Hash Utility",
        description="Add a SHA256 hashing utility with input validation.",
        priority=TaskPriority.HIGH,
        acceptance_criteria=["Must use hashlib.sha256", "Zero insecure MD5/SHA1 usage"],
    )


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# =====================================================================
# 1. Runner Initialization & Base Specialist
# =====================================================================


def test_runners_initialization() -> None:
    provider = MockAIProvider()
    architect = ArchitectRunner(provider)
    coder = CoderRunner(provider)
    auditor = SecurityAuditorRunner(provider)
    qa = QAEngineerRunner(provider)

    assert architect.role == AgentRole.ARCHITECT
    assert coder.role == AgentRole.CODER
    assert auditor.role == AgentRole.SECURITY_AUDITOR
    assert qa.role == AgentRole.QA_ENGINEER


# =====================================================================
# 2. Architect Runner
# =====================================================================


def test_architect_create_plan_default_fallback(sample_task: Task) -> None:
    # Default MockAIProvider returns generic dict without "steps"
    provider = MockAIProvider()
    architect = ArchitectRunner(provider)

    plan = architect.create_plan(sample_task)

    assert plan.task_id == sample_task.task_id
    assert len(plan.steps) == 1
    assert plan.steps[0].assigned_role == AgentRole.CODER
    assert plan.steps[0].step_id == "step_code"
    assert "sha256" in plan.steps[0].acceptance_criteria[0].lower()


def test_architect_create_plan_custom_steps(sample_task: Task) -> None:
    custom_plan_data = {
        "goal": "Build validated SHA256 utility",
        "steps": [
            {
                "step_id": "step_design",
                "assigned_role": "ARCHITECT",
                "title": "Design Hash API",
                "description": "Specify hashing function signatures.",
                "dependencies": [],
                "acceptance_criteria": ["Interface conforms to Hexagonal pattern."],
            },
            {
                "step_id": "step_impl",
                "assigned_role": "CODER",
                "title": "Implement Hash Function",
                "description": "Write SHA256 helper in Python.",
                "dependencies": ["step_design"],
                "acceptance_criteria": ["Clean type annotations.", "Passes AST checks."],
            },
        ],
    }
    provider = ConfigurableMockProvider(structured_data=custom_plan_data)
    architect = ArchitectRunner(provider)

    plan = architect.create_plan(sample_task)

    assert plan.goal == "Build validated SHA256 utility"
    assert len(plan.steps) == 2
    assert plan.steps[0].step_id == "step_design"
    assert plan.steps[0].assigned_role == AgentRole.ARCHITECT
    assert plan.steps[1].step_id == "step_impl"
    assert plan.steps[1].assigned_role == AgentRole.CODER
    assert plan.steps[1].dependencies == ["step_design"]


# =====================================================================
# 3. Coder Runner & CodeProposal Validation
# =====================================================================


def test_coder_generate_proposal_in_memory(sample_task: Task, temp_workspace: Path) -> None:
    code_data = {
        "target_path": "src/kanoman/crypto/hash_util.py",
        "proposed_content": "import hashlib\n\ndef compute_sha256(data: bytes) -> str:\n    return hashlib.sha256(data).hexdigest()\n",
        "rationale": "Implement SHA256 hash calculation using standard library.",
    }
    provider = ConfigurableMockProvider(structured_data=code_data)
    coder = CoderRunner(provider)

    step = AgentPlanStep(
        step_id="step_code_1",
        assigned_role=AgentRole.CODER,
        title="Write Hash Utility",
        description="Implement compute_sha256 function.",
    )

    # Count files before
    files_before = list(temp_workspace.rglob("*"))

    proposal = coder.generate_proposal(sample_task.task_id, step)

    # Invariant: Must NOT write directly to filesystem
    files_after = list(temp_workspace.rglob("*"))
    assert files_before == files_after

    assert isinstance(proposal, CodeProposal)
    assert proposal.target_path == "src/kanoman/crypto/hash_util.py"
    assert "compute_sha256" in proposal.proposed_content
    assert "SHA256" in proposal.rationale


def test_code_proposal_pydantic_validation() -> None:
    # Valid
    p = CodeProposal(
        target_path="src/kanoman/util.py",
        proposed_content="x = 1\n",
        rationale="Initialize x to 1.",
    )
    assert p.target_path == "src/kanoman/util.py"

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        CodeProposal(
            target_path="src/kanoman/util.py",
            proposed_content="x = 1\n",
            rationale="Initialize x.",
            extra_field="disallowed",  # type: ignore
        )

    # Short rationale (<5 chars) rejected
    with pytest.raises(ValidationError):
        CodeProposal(
            target_path="src/kanoman/util.py",
            proposed_content="x = 1\n",
            rationale="bad",
        )


# =====================================================================
# 4. Security Auditor Runner & Veto Invariant
# =====================================================================


def test_security_auditor_approves_clean_proposal(sample_task: Task) -> None:
    provider = ConfigurableMockProvider(
        structured_data={"decision_type": "APPROVE", "rationale": "Code conforms to security standards."}
    )
    auditor = SecurityAuditorRunner(provider)

    proposal = CodeProposal(
        target_path="src/kanoman/crypto/hash.py",
        proposed_content="import hashlib\n\ndef h(b: bytes) -> str:\n    return hashlib.sha256(b).hexdigest()\n",
        rationale="Secure SHA256 helper implementation.",
    )
    sec_dec = AgentDecision(
        task_id=sample_task.task_id,
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.APPROVE,
        is_approved=True,
        rationale="Clean proposal.",
    )
    qg_result = QualityGateResult(
        target_path=proposal.target_path,
        file_type="python",
        is_approved=True,
        findings=[],
        decision=sec_dec,
    )

    decision = auditor.evaluate_proposal(sample_task.task_id, proposal, qg_result)

    assert decision.is_approved is True
    assert decision.decision_type == DecisionType.APPROVE
    assert decision.agent_role == AgentRole.SECURITY_AUDITOR
    assert "security standards" in decision.rationale


def test_security_auditor_automatic_veto_on_quality_gate_failure(sample_task: Task) -> None:
    # Provider is configured to return APPROVE, but QualityGate FAILED.
    # HARD INVARIANT: Auditor MUST VETO automatically regardless of LLM inclination!
    provider = ConfigurableMockProvider(
        structured_data={"decision_type": "APPROVE", "rationale": "I want to approve anyway."}
    )
    auditor = SecurityAuditorRunner(provider)

    proposal = CodeProposal(
        target_path="src/kanoman/bad.py",
        proposed_content="eval('import os; os.system(\"rm -rf\")')\n",
        rationale="Dynamic code execution.",
    )
    from kanoman.analysis.models import Finding, FindingSeverity

    finding = Finding(
        rule_id="SEC001_EVAL_EXEC",
        severity=FindingSeverity.CRITICAL,
        message="Use of eval() detected.",
        file_path="src/kanoman/bad.py",
        line=1,
    )
    sec_dec = AgentDecision(
        task_id=sample_task.task_id,
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.REJECT,
        is_approved=False,
        rationale="Security finding detected.",
    )
    qg_result = QualityGateResult(
        target_path=proposal.target_path,
        file_type="python",
        is_approved=False,
        findings=[finding],
        decision=sec_dec,
    )

    decision = auditor.evaluate_proposal(sample_task.task_id, proposal, qg_result)

    # Invariant verified: Automatic veto
    assert decision.is_approved is False
    assert decision.decision_type == DecisionType.REJECT
    assert "VETO" in decision.rationale
    assert "SEC001_EVAL_EXEC" in decision.rationale
    assert provider.call_count == 0  # Did not even call provider!


def test_security_auditor_llm_rejection(sample_task: Task) -> None:
    provider = ConfigurableMockProvider(
        structured_data={"decision_type": "REJECT", "rationale": "High cyclomatic complexity and unhandled None."}
    )
    auditor = SecurityAuditorRunner(provider)

    proposal = CodeProposal(
        target_path="src/kanoman/complex.py",
        proposed_content="def func(x):\n    return x\n",
        rationale="Simple function.",
    )
    sec_dec = AgentDecision(
        task_id=sample_task.task_id,
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.APPROVE,
        is_approved=True,
        rationale="Passes AST.",
    )
    qg_result = QualityGateResult(
        target_path=proposal.target_path,
        file_type="python",
        is_approved=True,
        findings=[],
        decision=sec_dec,
    )

    decision = auditor.evaluate_proposal(sample_task.task_id, proposal, qg_result)

    assert decision.is_approved is False
    assert decision.decision_type == DecisionType.REJECT
    assert "complexity" in decision.rationale


# =====================================================================
# 5. QA Engineer Runner
# =====================================================================


def test_qa_engineer_evaluates_and_approves(sample_task: Task) -> None:
    provider = ConfigurableMockProvider(
        structured_data={"decision_type": "APPROVE", "rationale": "All acceptance criteria verified."}
    )
    qa = QAEngineerRunner(provider)

    step = AgentPlanStep(
        step_id="step_code_1",
        assigned_role=AgentRole.CODER,
        title="Implement hashing",
        description="SHA256 implementation.",
        acceptance_criteria=["Must use hashlib.sha256"],
    )
    proposal = CodeProposal(
        target_path="src/kanoman/crypto.py",
        proposed_content="import hashlib\n\ndef hash_val(v: bytes) -> str:\n    return hashlib.sha256(v).hexdigest()\n",
        rationale="Standard SHA256 helper.",
    )
    sec_decision = AgentDecision(
        task_id=sample_task.task_id,
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.APPROVE,
        is_approved=True,
        rationale="Security approved.",
    )

    qa_decision = qa.evaluate_verification(sample_task.task_id, step, proposal, sec_decision)

    assert qa_decision.is_approved is True
    assert qa_decision.decision_type == DecisionType.APPROVE
    assert qa_decision.agent_role == AgentRole.QA_ENGINEER


def test_qa_engineer_rejects_when_security_rejects(sample_task: Task) -> None:
    provider = ConfigurableMockProvider(
        structured_data={"decision_type": "APPROVE", "rationale": "I think it's okay."}
    )
    qa = QAEngineerRunner(provider)

    step = AgentPlanStep(
        step_id="step_code_1",
        assigned_role=AgentRole.CODER,
        title="Implement hashing",
        description="SHA256 implementation.",
    )
    proposal = CodeProposal(
        target_path="src/kanoman/crypto.py",
        proposed_content="bad code\n",
        rationale="Bad code proposal.",
    )
    sec_decision = AgentDecision(
        task_id=sample_task.task_id,
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.REJECT,
        is_approved=False,
        rationale="Security rejected proposal.",
    )

    qa_decision = qa.evaluate_verification(sample_task.task_id, step, proposal, sec_decision)

    assert qa_decision.is_approved is False
    assert qa_decision.decision_type == DecisionType.REJECT
    assert "Security Auditor has rejected" in qa_decision.rationale
    assert provider.call_count == 0  # Short-circuited without invoking provider


def test_qa_engineer_requests_changes(sample_task: Task) -> None:
    provider = ConfigurableMockProvider(
        structured_data={
            "decision_type": "REQUEST_CHANGES",
            "rationale": "Missing unit test coverage for edge case empty bytes.",
        }
    )
    qa = QAEngineerRunner(provider)

    step = AgentPlanStep(
        step_id="step_code_1",
        assigned_role=AgentRole.CODER,
        title="Implement hashing",
        description="SHA256 implementation.",
    )
    proposal = CodeProposal(
        target_path="src/kanoman/crypto.py",
        proposed_content="import hashlib\n\ndef hash_val(v: bytes) -> str:\n    return hashlib.sha256(v).hexdigest()\n",
        rationale="Standard SHA256 helper.",
    )
    sec_decision = AgentDecision(
        task_id=sample_task.task_id,
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.APPROVE,
        is_approved=True,
        rationale="Security approved.",
    )

    qa_decision = qa.evaluate_verification(sample_task.task_id, step, proposal, sec_decision)

    assert qa_decision.is_approved is False
    assert qa_decision.decision_type == DecisionType.REQUEST_CHANGES
    assert "edge case" in qa_decision.rationale


# =====================================================================
# 6. End-to-End Specialist Workflow: Success Path
# =====================================================================


def test_execute_end_to_end_specialist_workflow_success(sample_task: Task, temp_workspace: Path) -> None:
    # Configure clean proposal
    coder_data = {
        "target_path": "src/kanoman/crypto/hasher.py",
        "proposed_content": "import hashlib\n\ndef hash_token(data: str) -> str:\n    \"\"\"Compute SHA256 hex digest.\"\"\"\n    return hashlib.sha256(data.encode()).hexdigest()\n",
        "rationale": "Implemented robust hash_token utility.",
    }

    ai_provider = ConfigurableMockProvider(structured_data=coder_data)
    quality_gate = AgentQualityGate(workspace_root=temp_workspace)
    coordinator = MultiAgentCoordinator(quality_gate=quality_gate)
    architect = ArchitectRunner(ai_provider)
    coder = CoderRunner(ai_provider)
    auditor = SecurityAuditorRunner(ai_provider)
    qa = QAEngineerRunner(ai_provider)

    result = execute_end_to_end_specialist_workflow(
        task=sample_task,
        coordinator=coordinator,
        architect=architect,
        coder=coder,
        auditor=auditor,
        qa=qa,
        quality_gate=quality_gate,
    )

    assert result.status == CoordinatorStatus.COMPLETED
    assert result.is_successful is True
    assert len(result.decisions) >= 1
    assert result.decisions[0].is_approved is True

    # History audit trail contains messages
    assert len(coordinator.history) >= 1


# =====================================================================
# 7. End-to-End Workflow: Halting on Security Violation (eval/exec)
# =====================================================================


def test_execute_end_to_end_workflow_halts_on_security_violation(sample_task: Task, temp_workspace: Path) -> None:
    insecure_code_data = {
        "target_path": "src/kanoman/vuln.py",
        "proposed_content": "import os\n\ndef run_dyn(code_str: str):\n    eval(code_str)\n",
        "rationale": "Execute dynamic code using eval.",
    }

    ai_provider = ConfigurableMockProvider(structured_data=insecure_code_data)
    quality_gate = AgentQualityGate(workspace_root=temp_workspace)
    coordinator = MultiAgentCoordinator(quality_gate=quality_gate)
    architect = ArchitectRunner(ai_provider)
    coder = CoderRunner(ai_provider)
    auditor = SecurityAuditorRunner(ai_provider)
    qa = QAEngineerRunner(ai_provider)

    result = execute_end_to_end_specialist_workflow(
        task=sample_task,
        coordinator=coordinator,
        architect=architect,
        coder=coder,
        auditor=auditor,
        qa=qa,
        quality_gate=quality_gate,
    )

    # Invariant: Workflow MUST halt and result in REJECTED/FAILED
    assert result.status in (CoordinatorStatus.REJECTED, CoordinatorStatus.FAILED)
    assert result.is_successful is False
    # Decision rationale must capture the security veto
    veto_decisions = [d for d in result.decisions if d.agent_role == AgentRole.SECURITY_AUDITOR and not d.is_approved]
    assert len(veto_decisions) >= 1
    assert "VETO" in veto_decisions[0].rationale
    assert "PY_EVAL_EXEC" in veto_decisions[0].rationale


# =====================================================================
# 8. End-to-End Workflow: Halting on Syntax Error
# =====================================================================


def test_execute_end_to_end_workflow_halts_on_syntax_error(sample_task: Task, temp_workspace: Path) -> None:
    syntax_error_data = {
        "target_path": "src/kanoman/broken.py",
        "proposed_content": "def broken_syntax(:\n    pass\n",
        "rationale": "Introduce broken syntax.",
    }

    ai_provider = ConfigurableMockProvider(structured_data=syntax_error_data)
    quality_gate = AgentQualityGate(workspace_root=temp_workspace)
    coordinator = MultiAgentCoordinator(quality_gate=quality_gate)
    architect = ArchitectRunner(ai_provider)
    coder = CoderRunner(ai_provider)
    auditor = SecurityAuditorRunner(ai_provider)
    qa = QAEngineerRunner(ai_provider)

    result = execute_end_to_end_specialist_workflow(
        task=sample_task,
        coordinator=coordinator,
        architect=architect,
        coder=coder,
        auditor=auditor,
        qa=qa,
        quality_gate=quality_gate,
    )

    assert result.status in (CoordinatorStatus.REJECTED, CoordinatorStatus.FAILED)
    assert result.is_successful is False
    veto_decisions = [d for d in result.decisions if not d.is_approved]
    assert len(veto_decisions) >= 1
    assert "PY_SYNTAX_ERROR" in veto_decisions[0].rationale


# =====================================================================
# 9. Zero Direct Filesystem Writes Invariant
# =====================================================================


def test_zero_direct_filesystem_writes_during_workflow(sample_task: Task, temp_workspace: Path) -> None:
    # Snapshot existing files in workspace
    (temp_workspace / "existing_file.txt").write_text("baseline data", encoding="utf-8")
    initial_tree = sorted([p.name for p in temp_workspace.iterdir()])

    coder_data = {
        "target_path": "src/kanoman/crypto/mock.py",
        "proposed_content": "x = 42\n",
        "rationale": "Set constant x.",
    }

    ai_provider = ConfigurableMockProvider(structured_data=coder_data)
    quality_gate = AgentQualityGate(workspace_root=temp_workspace)
    coordinator = MultiAgentCoordinator(quality_gate=quality_gate)
    architect = ArchitectRunner(ai_provider)
    coder = CoderRunner(ai_provider)
    auditor = SecurityAuditorRunner(ai_provider)
    qa = QAEngineerRunner(ai_provider)

    execute_end_to_end_specialist_workflow(
        task=sample_task,
        coordinator=coordinator,
        architect=architect,
        coder=coder,
        auditor=auditor,
        qa=qa,
        quality_gate=quality_gate,
    )

    # Invariant: Filesystem unchanged
    current_tree = sorted([p.name for p in temp_workspace.iterdir()])
    assert current_tree == initial_tree
    assert not (temp_workspace / "src").exists()


# =====================================================================
# 10. Git Controller Veto Invariant: APPROVE does not grant Git commit/push
# =====================================================================


def test_git_controller_bypass_prevention_after_approval(sample_task: Task, temp_workspace: Path) -> None:
    coder_data = {
        "target_path": "src/kanoman/safe.py",
        "proposed_content": "SAFE = True\n",
        "rationale": "Completely safe code.",
    }

    ctrl = GitController(
        workspace_root=temp_workspace,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    ai_provider = ConfigurableMockProvider(structured_data=coder_data)
    quality_gate = AgentQualityGate(workspace_root=temp_workspace)
    coordinator = MultiAgentCoordinator(git_controller=ctrl, quality_gate=quality_gate)
    architect = ArchitectRunner(ai_provider)
    coder = CoderRunner(ai_provider)
    auditor = SecurityAuditorRunner(ai_provider)
    qa = QAEngineerRunner(ai_provider)

    result = execute_end_to_end_specialist_workflow(
        task=sample_task,
        coordinator=coordinator,
        architect=architect,
        coder=coder,
        auditor=auditor,
        qa=qa,
        quality_gate=quality_gate,
    )

    assert result.status == CoordinatorStatus.COMPLETED

    # HARD INVARIANT: Autonomous agents cannot commit or push
    with pytest.raises(PermissionError, match="Autonomous Git operation mode 'commit' is strictly prohibited"):
        coordinator.request_git_operation(
            mode="commit",
            files=["safe.py"],
            message="Agent commit",
        )

    with pytest.raises(PermissionError, match="Autonomous Git operation mode 'push' is strictly prohibited"):
        coordinator.request_git_operation(
            mode="push",
        )


# =====================================================================
# 11. Error Handling & Provider Edge Cases
# =====================================================================


def test_provider_error_handling_fails_closed(sample_task: Task) -> None:
    provider = ConfigurableMockProvider(simulate_error=AIErrorType.RATE_LIMIT_ERROR)
    architect = ArchitectRunner(provider)

    # Fail closed: Raises error, does not produce unverified plan
    with pytest.raises(AIException) as exc_info:
        architect.create_plan(sample_task)

    assert exc_info.value.error_type == AIErrorType.RATE_LIMIT_ERROR


def test_empty_or_malformed_provider_response(sample_task: Task) -> None:
    # Provider returns empty string content and no structured data
    provider = ConfigurableMockProvider(structured_data=None, raw_content="   ")
    architect = ArchitectRunner(provider)

    with pytest.raises(ValueError, match="empty structured response"):
        architect.create_plan(sample_task)


def test_secret_sanitization_in_error_logging(sample_task: Task, caplog: pytest.LogCaptureFixture) -> None:
    provider = ConfigurableMockProvider(structured_data=None, raw_content="Invalid JSON: AIzaSyDummySecretKey123")
    architect = ArchitectRunner(provider)

    with pytest.raises(Exception):
        architect.create_plan(sample_task)

    # Verify that secret in log was sanitized
    logged_text = caplog.text
    assert "AIzaSyDummySecretKey123" not in logged_text


# =====================================================================
# 12. Correlation ID & Audit Trail Consistency
# =====================================================================


def test_correlation_id_and_audit_trail_consistency(sample_task: Task, temp_workspace: Path) -> None:
    coder_data = {
        "target_path": "src/kanoman/audit.py",
        "proposed_content": "# Clean code\n",
        "rationale": "Audit test proposal.",
    }

    ai_provider = ConfigurableMockProvider(structured_data=coder_data)
    quality_gate = AgentQualityGate(workspace_root=temp_workspace)
    coordinator = MultiAgentCoordinator(quality_gate=quality_gate)
    architect = ArchitectRunner(ai_provider)
    coder = CoderRunner(ai_provider)
    auditor = SecurityAuditorRunner(ai_provider)
    qa = QAEngineerRunner(ai_provider)

    result = execute_end_to_end_specialist_workflow(
        task=sample_task,
        coordinator=coordinator,
        architect=architect,
        coder=coder,
        auditor=auditor,
        qa=qa,
        quality_gate=quality_gate,
    )

    assert result.task_id == sample_task.task_id

    # Verify every recorded decision in history has exact task_id and timestamps
    for dec in result.decisions:
        assert dec.task_id == sample_task.task_id
        assert dec.created_at is not None

    for msg in coordinator.history:
        assert msg.task_id == sample_task.task_id
        assert msg.created_at is not None
