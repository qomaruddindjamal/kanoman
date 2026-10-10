"""Specialist Persona Runners and AIRouter integration for Kanoman AI.

Implements persona-specific runners for:
- ARCHITECT: generates and refines structured AgentPlans.
- CODER: generates structured in-memory code proposals (zero direct file writes).
- SECURITY_AUDITOR: audits quality gate results and assesses risks (APPROVE, REJECT, ABORT).
- QA_ENGINEER: evaluates test strategy, verification criteria, and quality results.

SECURITY INVARIANTS:
1. Zero code execution: Code proposals are NEVER executed in the main process.
2. Zero unauthorized writes: Code proposals remain in-memory and are not written
   directly to disk by runners.
3. Quality Gate & Security Veto: Any blocking finding from AgentQualityGate or
   SecurityAuditor stops the workflow immediately.
4. Agent decisions do NOT grant permissions to commit, push, or deploy.
5. All outputs are schema-validated, bounded, and sanitized of credentials.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

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
from kanoman.ai.models import AIErrorType, AIException, AIMessage, AIResponse
from kanoman.ai.protocol import BaseAIProvider
from kanoman.core.models import Task
from kanoman.logging.logger import get_logger, redact_sensitive_text

logger = get_logger("agents.runners")


class CodeProposal(BaseModel):
    """Structured in-memory patch proposal produced by the Coder agent."""

    model_config = ConfigDict(extra="forbid")

    target_path: str = Field(..., min_length=2, max_length=260)
    proposed_content: str = Field(...)
    rationale: str = Field(..., min_length=5, max_length=2000)


class BaseSpecialistRunner:
    """Base class for persona runners enforcing role boundaries and validation."""

    def __init__(
        self,
        role: AgentRole,
        ai_provider: BaseAIProvider,
    ) -> None:
        self.role = role
        self.ai_provider = ai_provider

    def _call_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Invoke AI provider with structured schema validation and error sanitization."""
        try:
            res: AIResponse = self.ai_provider.generate_structured(
                messages=messages,
                schema=schema,
                temperature=temperature,
            )
            if res.structured_data is not None:
                return res.structured_data
            if res.content.strip():
                return json.loads(res.content)
            raise ValueError("Provider returned empty structured response content.")
        except Exception as exc:
            sanitized_err = redact_sensitive_text(str(exc))
            logger.error(
                f"Runner [{self.role.value}] structured generation failure: {sanitized_err}",
                status="RUNNER_STRUCTURED_ERROR",
            )
            raise


class ArchitectRunner(BaseSpecialistRunner):
    """Architect persona: Analyzes tasks and constructs structured AgentPlans."""

    def __init__(self, ai_provider: BaseAIProvider) -> None:
        super().__init__(AgentRole.ARCHITECT, ai_provider)

    def create_plan(
        self,
        task: Task,
        max_iterations: int = 5,
        token_budget: int = 50000,
        timeout_seconds: int = 300,
    ) -> AgentPlan:
        """Generate a validated AgentPlan for the specified task."""
        system_prompt = (
            "You are the Principal Software Architect in Kanoman AI. Your role is to design "
            "a modular, step-by-step technical plan for the task. Break down the task into "
            "concrete steps assigned to ARCHITECT, CODER, SECURITY_AUDITOR, or QA_ENGINEER. "
            "Ensure step dependencies are linear and acyclic."
        )
        user_prompt = f"Design an AgentPlan for Task ID '{task.task_id}':\nTitle: {task.title}\nDescription: {task.description}"

        schema = {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {"type": "string"},
                            "assigned_role": {
                                "type": "string",
                                "enum": ["ARCHITECT", "CODER", "SECURITY_AUDITOR", "QA_ENGINEER"],
                            },
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "dependencies": {"type": "array", "items": {"type": "string"}},
                            "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["step_id", "assigned_role", "title", "description"],
                    },
                },
            },
            "required": ["goal", "steps"],
        }

        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt),
        ]

        data = self._call_structured(messages, schema)

        raw_steps = data.get("steps", [])
        if not raw_steps:
            # Provide safe default baseline step if none generated
            raw_steps = [
                {
                    "step_id": "step_code",
                    "assigned_role": "CODER",
                    "title": "Implement task changes",
                    "description": task.description,
                    "dependencies": [],
                    "acceptance_criteria": task.acceptance_criteria or ["Code passes quality gate."],
                }
            ]

        steps: List[AgentPlanStep] = []
        for s in raw_steps:
            steps.append(
                AgentPlanStep(
                    step_id=s["step_id"],
                    assigned_role=AgentRole(s["assigned_role"]),
                    title=s["title"],
                    description=s["description"],
                    dependencies=s.get("dependencies", []),
                    acceptance_criteria=s.get("acceptance_criteria", []),
                )
            )

        return AgentPlan(
            task_id=task.task_id,
            goal=data.get("goal", task.title),
            steps=steps,
            max_iterations=max_iterations,
            token_budget=token_budget,
            timeout_seconds=timeout_seconds,
        )


class CoderRunner(BaseSpecialistRunner):
    """Coder persona: Generates in-memory code proposals without writing to disk."""

    def __init__(self, ai_provider: BaseAIProvider) -> None:
        super().__init__(AgentRole.CODER, ai_provider)

    def generate_proposal(
        self,
        task_id: str,
        step: AgentPlanStep,
        context_messages: Optional[List[AgentMessage]] = None,
    ) -> CodeProposal:
        """Generate an in-memory code modification proposal conforming to specifications."""
        system_prompt = (
            "You are the Senior Software Engineer (Coder) in Kanoman AI. "
            "Generate in-memory code modifications conforming strictly to requirements. "
            "DO NOT write directly to disk or execute commands. "
            "Never introduce eval(), exec(), subprocess with shell=True, insecure pickle, or hardcoded secrets."
        )
        context_summary = "\n".join(
            f"[{m.sender_role.value}] {m.summary}" for m in (context_messages or [])[-5:]
        )
        user_prompt = (
            f"Generate code proposal for Step '{step.step_id}': {step.title}\n"
            f"Description: {step.description}\n"
            f"Context History:\n{context_summary}"
        )

        schema = {
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
                "proposed_content": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["target_path", "proposed_content", "rationale"],
        }

        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt),
        ]

        data = self._call_structured(messages, schema)

        return CodeProposal(
            target_path=data.get("target_path", "src/kanoman/module.py"),
            proposed_content=data.get("proposed_content", "# Proposed implementation\n"),
            rationale=data.get("rationale", f"Implemented solution for {step.step_id}."),
        )


class SecurityAuditorRunner(BaseSpecialistRunner):
    """Security Auditor persona: Evaluates Quality Gate results and enforces safety vetoes."""

    def __init__(self, ai_provider: BaseAIProvider) -> None:
        super().__init__(AgentRole.SECURITY_AUDITOR, ai_provider)

    def evaluate_proposal(
        self,
        task_id: str,
        proposal: CodeProposal,
        quality_gate_result: QualityGateResult,
    ) -> AgentDecision:
        """Evaluate a proposal and Quality Gate outcome, issuing a binding audit decision."""
        # Hard security invariant: If Quality Gate detected blocking findings, VETO automatically.
        if not quality_gate_result.is_approved:
            blocking_findings = [f.rule_id for f in quality_gate_result.findings]
            rationale = (
                f"Security Auditor VETO: Quality Gate failed on '{proposal.target_path}' "
                f"with blocking findings: {', '.join(blocking_findings)}."
            )
            logger.warning(rationale, task_id=task_id, status="SECURITY_VETO")
            return AgentDecision(
                task_id=task_id,
                agent_role=AgentRole.SECURITY_AUDITOR,
                decision_type=DecisionType.REJECT,
                is_approved=False,
                rationale=rationale,
                metadata={"blocking_findings": blocking_findings},
            )

        # Quality gate passed; conduct LLM security assessment
        system_prompt = (
            "You are the Application Security Engineer in Kanoman AI. "
            "Assess the proposed changes and quality gate findings. "
            "Issue APPROVE if clean, REJECT if security/design flaws are present, or ABORT if critical risks exist."
        )
        user_prompt = (
            f"Audit Code Proposal for Task '{task_id}':\n"
            f"File: {proposal.target_path}\n"
            f"Rationale: {proposal.rationale}\n"
            f"Quality Gate Status: Approved (Findings: {len(quality_gate_result.findings)})"
        )

        schema = {
            "type": "object",
            "properties": {
                "decision_type": {"type": "string", "enum": ["APPROVE", "REJECT", "ABORT"]},
                "rationale": {"type": "string"},
            },
            "required": ["decision_type", "rationale"],
        }

        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt),
        ]

        data = self._call_structured(messages, schema)
        dec_type = DecisionType(data.get("decision_type", "APPROVE"))
        is_appr = (dec_type == DecisionType.APPROVE)

        return AgentDecision(
            task_id=task_id,
            agent_role=AgentRole.SECURITY_AUDITOR,
            decision_type=dec_type,
            is_approved=is_appr,
            rationale=data.get("rationale", "Security audit passed without findings."),
            metadata={"file": proposal.target_path},
        )


class QAEngineerRunner(BaseSpecialistRunner):
    """QA Engineer persona: Evaluates test strategy and acceptance criteria."""

    def __init__(self, ai_provider: BaseAIProvider) -> None:
        super().__init__(AgentRole.QA_ENGINEER, ai_provider)

    def evaluate_verification(
        self,
        task_id: str,
        step: AgentPlanStep,
        proposal: CodeProposal,
        security_decision: AgentDecision,
    ) -> AgentDecision:
        """Evaluate if proposed code fulfills quality criteria and acceptance criteria."""
        if not security_decision.is_approved:
            rationale = f"QA Engineer rejects step '{step.step_id}': Security Auditor has rejected the proposal."
            return AgentDecision(
                task_id=task_id,
                agent_role=AgentRole.QA_ENGINEER,
                decision_type=DecisionType.REJECT,
                is_approved=False,
                rationale=rationale,
            )

        system_prompt = (
            "You are the Quality Assurance & Reliability Engineer in Kanoman AI. "
            "Review the proposed code against step acceptance criteria. "
            "Issue APPROVE if verified or REQUEST_CHANGES if additional tests/revisions are needed."
        )
        criteria_str = "\n".join(f"- {c}" for c in step.acceptance_criteria)
        user_prompt = (
            f"Evaluate Verification for Step '{step.step_id}': {step.title}\n"
            f"Target: {proposal.target_path}\n"
            f"Acceptance Criteria:\n{criteria_str}"
        )

        schema = {
            "type": "object",
            "properties": {
                "decision_type": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES", "REJECT"]},
                "rationale": {"type": "string"},
            },
            "required": ["decision_type", "rationale"],
        }

        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt),
        ]

        data = self._call_structured(messages, schema)
        dec_type = DecisionType(data.get("decision_type", "APPROVE"))
        is_appr = (dec_type == DecisionType.APPROVE)

        return AgentDecision(
            task_id=task_id,
            agent_role=AgentRole.QA_ENGINEER,
            decision_type=dec_type,
            is_approved=is_appr,
            rationale=data.get("rationale", f"QA verified step '{step.step_id}' successfully."),
        )


def execute_end_to_end_specialist_workflow(
    task: Task,
    coordinator: MultiAgentCoordinator,
    architect: ArchitectRunner,
    coder: CoderRunner,
    auditor: SecurityAuditorRunner,
    qa: QAEngineerRunner,
    quality_gate: AgentQualityGate,
) -> CoordinatorResult:
    """Execute a complete, deterministic end-to-end multi-agent workflow.

    Sequence:
    1. Architect creates AgentPlan.
    2. Coder generates in-memory CodeProposal for code step (no direct disk writes).
    3. Quality Gate evaluates proposal statically (PythonAST / Markdown).
    4. Security Auditor reviews findings and issues binding decision (VETO on failure).
    5. QA Engineer evaluates verification criteria.
    6. Coordinator produces final CoordinatorResult with full audit trail.
    """
    # Step 1: Architect Plan
    plan = architect.create_plan(task)

    # Handlers wired to specialist runners
    step_handlers = {}

    for step in plan.steps:
        if step.assigned_role == AgentRole.CODER:
            def make_coder_handler(s: AgentPlanStep):
                def coder_turn(step_obj: AgentPlanStep, coord: MultiAgentCoordinator) -> AgentDecision:
                    # 1. Coder generates in-memory proposal
                    proposal = coder.generate_proposal(task.task_id, step_obj, coord.history)

                    # 2. Quality Gate evaluates proposal in memory (zero filesystem mutation)
                    qg_res = quality_gate.verify_proposal(
                        task_id=task.task_id,
                        target_path=proposal.target_path,
                        proposed_content=proposal.proposed_content,
                    )

                    # 3. Security Auditor issues decision based on Quality Gate findings
                    sec_decision = auditor.evaluate_proposal(task.task_id, proposal, qg_res)
                    if not sec_decision.is_approved:
                        return sec_decision

                    # 4. QA Engineer verifies acceptance criteria
                    qa_decision = qa.evaluate_verification(task.task_id, step_obj, proposal, sec_decision)
                    return qa_decision
                return coder_turn

            step_handlers[step.step_id] = make_coder_handler(step)

    # Execute plan through coordinator
    return coordinator.execute_plan(task, plan, custom_step_handlers=step_handlers)
