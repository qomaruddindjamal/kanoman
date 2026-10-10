"""Domain models and message contracts for Kanoman AI Multi-Agent Orchestration.

Defines AgentRole, AgentMessage, AgentDecision, and AgentPlan with strict Pydantic v2
validation, extra="forbid" policy, bounded payload sizes, timezone-aware datetime handling,
and credential sanitization.

IMPORTANT SECURITY INVARIANTS:
1. Agent decisions and plans are declarative audit artifacts; they do NOT grant
   automatic permissions to commit, push, deploy, or bypass GitController.
2. Static AST analysis and model validation are not execution sandboxes.
3. Secret patterns are proactively sanitized across messages and payloads.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from kanoman.logging.logger import redact_sensitive_text

ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")
MAX_PAYLOAD_SERIALIZED_BYTES = 65536  # 64 KB limit for payload contents
MAX_PAYLOAD_DEPTH = 5


def _validate_id(identifier: str, field_name: str) -> str:
    clean = identifier.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty.")
    if not ID_REGEX.match(clean):
        raise ValueError(
            f"Invalid {field_name} format: '{clean}'. Must contain only alphanumeric, underscore, or hyphen."
        )
    return clean


def _normalize_datetime(dt: Any) -> datetime:
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            raise ValueError("Timestamp must be a valid ISO format datetime string.")
    elif not isinstance(dt, datetime):
        raise ValueError("Timestamp must be a datetime object or valid ISO string.")

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _check_dict_depth(obj: Any, current_depth: int = 1) -> None:
    if current_depth > MAX_PAYLOAD_DEPTH:
        raise ValueError(
            f"Payload nesting depth exceeds maximum allowed limit of {MAX_PAYLOAD_DEPTH} levels."
        )
    if isinstance(obj, dict):
        for val in obj.values():
            if isinstance(val, (dict, list)):
                _check_dict_depth(val, current_depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _check_dict_depth(item, current_depth + 1)


def _sanitize_data(obj: Any) -> Any:
    """Recursively redact sensitive patterns in string values."""
    if isinstance(obj, str):
        return redact_sensitive_text(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_data(item) for item in obj]
    return obj


class AgentRole(str, Enum):
    """Recognized agent persona roles in Kanoman AI multi-agent hierarchy."""

    ARCHITECT = "ARCHITECT"
    CODER = "CODER"
    SECURITY_AUDITOR = "SECURITY_AUDITOR"
    QA_ENGINEER = "QA_ENGINEER"


class MessageType(str, Enum):
    """Explicit intent categories for inter-agent communication."""

    PROPOSAL = "PROPOSAL"
    REVIEW = "REVIEW"
    QUERY = "QUERY"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    INFORMATIONAL = "INFORMATIONAL"


class DecisionType(str, Enum):
    """Explicit categories for structured agent decisions."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    ABORT = "ABORT"


class AgentMessage(BaseModel):
    """Validated message contract for structured communication between persona agents.

    Messages are transport payloads across agents. They do not convey authorization;
    all task state changes remain under the strict control of the central coordinator.
    """

    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    task_id: str = Field(..., min_length=3, max_length=64)
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}", max_length=64)
    sender_role: AgentRole = Field(..., description="Role of the transmitting agent.")
    recipient_role: Optional[AgentRole] = Field(
        default=None,
        description="Target agent role, or None if broadcast to the coordinator.",
    )
    message_type: MessageType = Field(default=MessageType.INFORMATIONAL)
    summary: str = Field(..., min_length=3, max_length=500)
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, str] = Field(
        default_factory=dict,
        description="Audit metadata documenting origin (e.g. source_step, model_provider).",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("message_id", "task_id", "correlation_id")
    @classmethod
    def validate_ids(cls, v: str, info: Any) -> str:
        return _validate_id(v, info.field_name)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Any) -> datetime:
        return _normalize_datetime(v)

    @field_validator("payload")
    @classmethod
    def validate_payload_bounds(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        _check_dict_depth(v)
        try:
            serialized = json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Payload contains non-serializable content: {str(e)}")

        if len(serialized.encode("utf-8")) > MAX_PAYLOAD_SERIALIZED_BYTES:
            raise ValueError(
                f"Payload size ({len(serialized)} bytes) exceeds maximum limit of "
                f"{MAX_PAYLOAD_SERIALIZED_BYTES} bytes."
            )
        return v

    @model_validator(mode="after")
    def sanitize_secrets(self) -> AgentMessage:
        object.__setattr__(self, "summary", redact_sensitive_text(self.summary))
        object.__setattr__(self, "payload", _sanitize_data(self.payload))
        sanitized_prov = {k: redact_sensitive_text(str(v)) for k, v in self.provenance.items()}
        object.__setattr__(self, "provenance", sanitized_prov)
        return self


class AgentDecision(BaseModel):
    """Structured record of an agent's technical evaluation or audit outcome.

    Decisions serve as audit trails. They do NOT automatically grant commit, push,
    deployment, or authority to bypass the GitController or TaskOrchestrator.
    """

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}")
    task_id: str = Field(..., min_length=3, max_length=64)
    message_id: Optional[str] = Field(default=None, max_length=64)
    agent_role: AgentRole = Field(..., description="Role of the agent issuing this decision.")
    decision_type: DecisionType = Field(...)
    is_approved: bool = Field(..., description="True if the proposal is considered acceptable.")
    rationale: str = Field(..., min_length=5, max_length=2000)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("decision_id", "task_id")
    @classmethod
    def validate_required_ids(cls, v: str, info: Any) -> str:
        return _validate_id(v, info.field_name)

    @field_validator("message_id")
    @classmethod
    def validate_optional_message_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_id(v, "message_id")
        return None

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Any) -> datetime:
        return _normalize_datetime(v)

    @model_validator(mode="after")
    def sanitize_rationale(self) -> AgentDecision:
        object.__setattr__(self, "rationale", redact_sensitive_text(self.rationale))
        object.__setattr__(self, "metadata", _sanitize_data(self.metadata))
        return self


class AgentPlanStep(BaseModel):
    """Single declarative step in an orchestrated multi-agent plan."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(..., min_length=2, max_length=32)
    assigned_role: AgentRole = Field(...)
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=5, max_length=2000)
    dependencies: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, v: str) -> str:
        return _validate_id(v, "step_id")

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, v: List[str]) -> List[str]:
        return [_validate_id(dep, "dependency_id") for dep in v]


class AgentPlan(BaseModel):
    """Audited, declarative execution plan constructed by the Architect agent.

    An AgentPlan is a proposal structure; execution remains governed by the central
    orchestrator adhering to cycle limits and token budgets.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    task_id: str = Field(..., min_length=3, max_length=64)
    goal: str = Field(..., min_length=5, max_length=500)
    steps: List[AgentPlanStep] = Field(..., min_length=1, max_length=50)
    max_iterations: int = Field(default=5, ge=1, le=20)
    token_budget: int = Field(default=50000, ge=100, le=1000000)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("plan_id", "task_id")
    @classmethod
    def validate_plan_ids(cls, v: str, info: Any) -> str:
        return _validate_id(v, info.field_name)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Any) -> datetime:
        return _normalize_datetime(v)

    @model_validator(mode="after")
    def validate_step_dependencies(self) -> AgentPlan:
        step_ids = {s.step_id for s in self.steps}
        for s in self.steps:
            for dep in s.dependencies:
                if dep not in step_ids:
                    raise ValueError(
                        f"Step '{s.step_id}' references unknown dependency step '{dep}'."
                    )
                if dep == s.step_id:
                    raise ValueError(f"Step '{s.step_id}' cannot depend on itself.")
        return self
