"""Comprehensive unit tests for Multi-Agent domain models and message contracts."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from kanoman.agents.models import (
    AgentRole,
    MessageType,
    DecisionType,
    AgentMessage,
    AgentDecision,
    AgentPlanStep,
    AgentPlan,
)


# =====================================================================
# 1. Valid Model Creation
# =====================================================================

def test_agent_role_enum_values():
    assert AgentRole.ARCHITECT.value == "ARCHITECT"
    assert AgentRole.CODER.value == "CODER"
    assert AgentRole.SECURITY_AUDITOR.value == "SECURITY_AUDITOR"
    assert AgentRole.QA_ENGINEER.value == "QA_ENGINEER"


def test_valid_agent_message_creation():
    msg = AgentMessage(
        task_id="task_12345",
        sender_role=AgentRole.ARCHITECT,
        recipient_role=AgentRole.CODER,
        message_type=MessageType.PROPOSAL,
        summary="Architecture proposal for module X",
        payload={"module": "auth", "methods": ["login", "logout"]},
        provenance={"origin": "step_1", "model": "gemini-2.5-flash"},
    )
    assert msg.message_id.startswith("msg_")
    assert msg.task_id == "task_12345"
    assert msg.sender_role == AgentRole.ARCHITECT
    assert msg.recipient_role == AgentRole.CODER
    assert msg.message_type == MessageType.PROPOSAL
    assert msg.summary == "Architecture proposal for module X"
    assert msg.created_at.tzinfo == timezone.utc


def test_valid_agent_decision_creation():
    dec = AgentDecision(
        task_id="task_12345",
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.APPROVE,
        is_approved=True,
        rationale="Static AST analysis and secret scans completed cleanly.",
        metadata={"scanner": "PythonASTAnalyzer", "findings": 0},
    )
    assert dec.decision_id.startswith("dec_")
    assert dec.is_approved is True
    assert dec.decision_type == DecisionType.APPROVE
    assert dec.created_at.tzinfo == timezone.utc


def test_valid_agent_plan_creation():
    step1 = AgentPlanStep(
        step_id="step_arch",
        assigned_role=AgentRole.ARCHITECT,
        title="Design architecture",
        description="Draft interfaces and data models",
    )
    step2 = AgentPlanStep(
        step_id="step_code",
        assigned_role=AgentRole.CODER,
        title="Implement code",
        description="Write source files conforming to specification",
        dependencies=["step_arch"],
    )
    plan = AgentPlan(
        task_id="task_12345",
        goal="Build secure token authentication service",
        steps=[step1, step2],
        max_iterations=3,
        token_budget=20000,
        timeout_seconds=120,
    )
    assert plan.plan_id.startswith("plan_")
    assert len(plan.steps) == 2
    assert plan.steps[1].dependencies == ["step_arch"]
    assert plan.created_at.tzinfo == timezone.utc


# =====================================================================
# 2. Invalid Role and Decision Type Rejection
# =====================================================================

def test_invalid_agent_role_rejected():
    with pytest.raises(ValidationError):
        AgentMessage(
            task_id="task_12345",
            sender_role="HACKER",  # type: ignore
            summary="Invalid role test",
        )


def test_invalid_decision_type_rejected():
    with pytest.raises(ValidationError):
        AgentDecision(
            task_id="task_12345",
            agent_role=AgentRole.SECURITY_AUDITOR,
            decision_type="MAYBE",  # type: ignore
            is_approved=False,
            rationale="Unrecognized decision type",
        )


# =====================================================================
# 3. Missing Mandatory Fields Rejection
# =====================================================================

def test_missing_mandatory_fields_in_message():
    with pytest.raises(ValidationError) as exc_info:
        AgentMessage()  # type: ignore
    errors = str(exc_info.value)
    assert "task_id" in errors
    assert "sender_role" in errors
    assert "summary" in errors


def test_missing_mandatory_fields_in_decision():
    with pytest.raises(ValidationError) as exc_info:
        AgentDecision()  # type: ignore
    errors = str(exc_info.value)
    assert "task_id" in errors
    assert "agent_role" in errors
    assert "decision_type" in errors
    assert "is_approved" in errors
    assert "rationale" in errors


def test_missing_mandatory_fields_in_plan():
    with pytest.raises(ValidationError) as exc_info:
        AgentPlan()  # type: ignore
    errors = str(exc_info.value)
    assert "task_id" in errors
    assert "goal" in errors
    assert "steps" in errors


# =====================================================================
# 4. Payload Structure, Bounds and Depth Validation
# =====================================================================

def test_payload_exceeding_max_depth_rejected():
    # Construct a nested dictionary exceeding 5 levels
    deep_payload = {"l1": {"l2": {"l3": {"l4": {"l5": {"l6": "too deep"}}}}}}
    with pytest.raises(ValidationError, match="nesting depth exceeds maximum allowed limit"):
        AgentMessage(
            task_id="task_12345",
            sender_role=AgentRole.CODER,
            summary="Deep payload test",
            payload=deep_payload,
        )


def test_payload_exceeding_byte_limit_rejected():
    # Construct payload larger than 64KB (65536 bytes)
    huge_payload = {"data": "X" * 70000}
    with pytest.raises(ValidationError, match="exceeds maximum limit"):
        AgentMessage(
            task_id="task_12345",
            sender_role=AgentRole.CODER,
            summary="Huge payload test",
            payload=huge_payload,
        )


def test_payload_non_serializable_rejected():
    class CustomObject:
        pass

    with pytest.raises(ValidationError, match="non-serializable"):
        AgentMessage(
            task_id="task_12345",
            sender_role=AgentRole.CODER,
            summary="Non serializable test",
            payload={"obj": CustomObject()},
        )


# =====================================================================
# 5. Extra Fields Policy ("extra=forbid")
# =====================================================================

def test_extra_fields_forbidden_in_message():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentMessage(
            task_id="task_12345",
            sender_role=AgentRole.ARCHITECT,
            summary="Extra field test",
            unauthorized_field="malicious_payload",  # type: ignore
        )


def test_extra_fields_forbidden_in_decision():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentDecision(
            task_id="task_12345",
            agent_role=AgentRole.SECURITY_AUDITOR,
            decision_type=DecisionType.APPROVE,
            is_approved=True,
            rationale="Rationale text",
            bypass_security=True,  # type: ignore
        )


def test_extra_fields_forbidden_in_plan():
    step = AgentPlanStep(
        step_id="step_1",
        assigned_role=AgentRole.ARCHITECT,
        title="Title",
        description="Valid description",
    )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentPlan(
            task_id="task_12345",
            goal="Goal description",
            steps=[step],
            extra_field="rejected",  # type: ignore
        )


# =====================================================================
# 6. Timezone Handling & Normalization
# =====================================================================

def test_naive_datetime_normalized_to_utc():
    naive_dt = datetime(2026, 10, 10, 12, 0, 0)
    msg = AgentMessage(
        task_id="task_12345",
        sender_role=AgentRole.ARCHITECT,
        summary="Naive dt test",
        created_at=naive_dt,
    )
    assert msg.created_at.tzinfo == timezone.utc
    assert msg.created_at.hour == 12


def test_invalid_datetime_type_rejected():
    with pytest.raises(ValidationError, match="Timestamp must be a datetime object or valid ISO string"):
        AgentMessage(
            task_id="task_12345",
            sender_role=AgentRole.ARCHITECT,
            summary="Bad timestamp test",
            created_at=123456789,  # type: ignore
        )


# =====================================================================
# 7. Serialization and Deserialization Roundtrips
# =====================================================================

def test_agent_message_serialization_roundtrip():
    msg = AgentMessage(
        task_id="task_12345",
        sender_role=AgentRole.ARCHITECT,
        recipient_role=AgentRole.CODER,
        summary="Roundtrip message",
        payload={"key": "val", "count": 42},
    )
    dumped_json = msg.model_dump_json()
    loaded = AgentMessage.model_validate_json(dumped_json)
    assert loaded.message_id == msg.message_id
    assert loaded.task_id == msg.task_id
    assert loaded.payload == msg.payload
    assert loaded.created_at == msg.created_at


def test_agent_plan_serialization_roundtrip():
    step = AgentPlanStep(
        step_id="step_1",
        assigned_role=AgentRole.CODER,
        title="Code step",
        description="Implementation details",
    )
    plan = AgentPlan(
        task_id="task_9999",
        goal="Execute plan",
        steps=[step],
    )
    dumped_json = plan.model_dump_json()
    loaded = AgentPlan.model_validate_json(dumped_json)
    assert loaded.plan_id == plan.plan_id
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == "step_1"


# =====================================================================
# 8. ID & Step Dependency Validation
# =====================================================================

def test_invalid_id_characters_rejected():
    with pytest.raises(ValidationError, match="Must contain only alphanumeric"):
        AgentMessage(
            task_id="invalid task id with spaces!",
            sender_role=AgentRole.ARCHITECT,
            summary="Bad id test",
        )


def test_plan_step_unknown_dependency_rejected():
    step1 = AgentPlanStep(
        step_id="step_1",
        assigned_role=AgentRole.ARCHITECT,
        title="Title",
        description="Valid description",
        dependencies=["non_existent_step"],
    )
    with pytest.raises(ValidationError, match="references unknown dependency step"):
        AgentPlan(
            task_id="task_12345",
            goal="Plan with bad dependency",
            steps=[step1],
        )


def test_plan_step_self_dependency_rejected():
    step1 = AgentPlanStep(
        step_id="step_1",
        assigned_role=AgentRole.ARCHITECT,
        title="Title",
        description="Valid description",
        dependencies=["step_1"],
    )
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        AgentPlan(
            task_id="task_12345",
            goal="Plan with self dependency",
            steps=[step1],
        )


# =====================================================================
# 9. No Cross-Instance Mutable Defaults
# =====================================================================

def test_no_cross_instance_mutable_defaults():
    msg1 = AgentMessage(
        task_id="task_1",
        sender_role=AgentRole.ARCHITECT,
        summary="Msg 1",
    )
    msg2 = AgentMessage(
        task_id="task_2",
        sender_role=AgentRole.CODER,
        summary="Msg 2",
    )
    msg1.payload["mutated_key"] = "mutated_value"
    assert "mutated_key" not in msg2.payload
    assert msg2.payload == {}


# =====================================================================
# 10. Proactive Credential Sanitization
# =====================================================================

def test_secret_sanitization_in_summary_and_payload():
    ghp_token = "gh" + "p_" + ("a" * 25)
    gemini_key = "AI" + "za" + ("c" * 35)
    sk_key = "s" + "k-" + ("b" * 25)
    msg = AgentMessage(
        task_id="task_sec",
        sender_role=AgentRole.CODER,
        summary=f"Sending token {ghp_token} for login",
        payload={
            "api_key": gemini_key,
            "nested": {
                "token": sk_key
            }
        },
        provenance={"debug_info": f"Used key {ghp_token}"},
    )
    # Check that secrets are masked with ***REDACTED_SECRET***
    assert ghp_token not in msg.summary
    assert "***REDACTED_SECRET***" in msg.summary
    assert gemini_key not in msg.payload["api_key"]
    assert "***REDACTED_SECRET***" in msg.payload["api_key"]
    assert sk_key not in msg.payload["nested"]["token"]
    assert "***REDACTED_SECRET***" in msg.payload["nested"]["token"]
    assert ghp_token not in msg.provenance["debug_info"]
    assert "***REDACTED_SECRET***" in msg.provenance["debug_info"]


def test_secret_sanitization_in_decision_rationale():
    ghp_token = "gh" + "p_" + ("d" * 25)
    dec = AgentDecision(
        task_id="task_sec",
        agent_role=AgentRole.SECURITY_AUDITOR,
        decision_type=DecisionType.REJECT,
        is_approved=False,
        rationale=f"Found leaked secret {ghp_token} in PR",
    )
    assert ghp_token not in dec.rationale
    assert "***REDACTED_SECRET***" in dec.rationale
