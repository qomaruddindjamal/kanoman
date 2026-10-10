"""Quality Gate Adapter for Agent Proposals in Kanoman AI.

Enforces static analysis over code (.py) and documentation (.md) proposals using
PythonASTAnalyzer and MarkdownValidator before agent proposals can proceed to review.
Determines file type from validated file paths (not agent claims), blocks path traversal
and symlink escapes, and operates in fail-closed mode.

IMPORTANT SECURITY INVARIANTS:
1. Zero code execution: Static AST analysis inspects syntactic trees; target code
   is NEVER imported or executed in the runtime process.
2. Static AST analysis is NOT an execution sandbox.
3. Agents CANNOT disable, bypass, or override the quality gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field

from kanoman.agents.models import AgentDecision, AgentRole, DecisionType
from kanoman.analysis.markdown_validator import MarkdownValidator
from kanoman.analysis.models import Finding, FindingSeverity
from kanoman.analysis.python_analyzer import PythonASTAnalyzer
from kanoman.logging.logger import get_logger, redact_sensitive_text

logger = get_logger("agents.quality_gate")


class QualityGateResult(BaseModel):
    """Structured, immutable audit result of a quality gate evaluation."""

    model_config = ConfigDict(extra="forbid")

    target_path: str
    file_type: str
    is_approved: bool
    findings: List[Finding] = Field(default_factory=list)
    decision: AgentDecision
    details: Optional[str] = None


class AgentQualityGate:
    """Quality gate validating agent-proposed file contents before approval."""

    def __init__(
        self,
        workspace_root: Path,
        python_analyzer: Optional[PythonASTAnalyzer] = None,
        markdown_validator: Optional[MarkdownValidator] = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.python_analyzer = python_analyzer or PythonASTAnalyzer(self.workspace_root)
        self.markdown_validator = markdown_validator or MarkdownValidator(self.workspace_root)

    def validate_target_path(self, target_path: Union[str, Path]) -> Tuple[Path, str]:
        """Validate target path against path traversal, symlink escape, and unsupported types."""
        path_str = str(target_path).strip()
        if not path_str:
            raise ValueError("Target path cannot be empty.")

        p = Path(path_str)
        if p.is_absolute() or (len(path_str) > 1 and path_str[1] == ":"):
            raise ValueError(f"Absolute paths are prohibited in quality gate: '{path_str}'")

        if ".." in p.parts:
            raise ValueError(f"Path traversal detected in path: '{path_str}'")

        resolved = (self.workspace_root / p).resolve()
        if self.workspace_root not in resolved.parents and resolved != self.workspace_root:
            raise ValueError(
                f"Path traversal detected: '{path_str}' resolves outside workspace root '{self.workspace_root}'"
            )

        # Check symlink escape if file exists and is a symlink
        if (self.workspace_root / p).is_symlink():
            real_target = (self.workspace_root / p).resolve()
            if self.workspace_root not in real_target.parents and real_target != self.workspace_root:
                raise ValueError(
                    f"Symlink escape detected: '{path_str}' points outside workspace root to '{real_target}'"
                )

        ext = p.suffix.lower()
        if ext == ".py":
            file_type = "python"
        elif ext == ".md":
            file_type = "markdown"
        else:
            raise ValueError(
                f"Unsupported file extension '{ext}' for quality gate validation. Permitted: .py, .md"
            )

        return resolved, file_type

    def verify_proposal(
        self,
        task_id: str,
        target_path: str,
        proposed_content: str,
    ) -> QualityGateResult:
        """Verify an in-memory file proposal against static quality gate rules."""
        try:
            _, file_type = self.validate_target_path(target_path)
            findings: List[Finding] = []

            if file_type == "python":
                findings = self.python_analyzer.analyze_source(
                    proposed_content, file_path_str=target_path
                )
            elif file_type == "markdown":
                findings = self.markdown_validator.validate_content(
                    proposed_content, file_path_str=target_path
                )

            # Check for blocking findings (MEDIUM, HIGH, or CRITICAL severity)
            blocking_findings = [
                f for f in findings
                if f.severity in {FindingSeverity.MEDIUM, FindingSeverity.HIGH, FindingSeverity.CRITICAL}
            ]

            if blocking_findings:
                rule_ids = ", ".join(f.rule_id for f in blocking_findings)
                rationale = (
                    f"Quality gate rejected proposal '{target_path}' due to {len(blocking_findings)} "
                    f"blocking finding(s): {rule_ids}."
                )
                decision = AgentDecision(
                    task_id=task_id,
                    agent_role=AgentRole.SECURITY_AUDITOR,
                    decision_type=DecisionType.REJECT,
                    is_approved=False,
                    rationale=rationale,
                    metadata={"blocking_count": len(blocking_findings)},
                )
                logger.warning(rationale, task_id=task_id, status="QUALITY_GATE_REJECTED")
                return QualityGateResult(
                    target_path=target_path,
                    file_type=file_type,
                    is_approved=False,
                    findings=findings,
                    decision=decision,
                    details=rationale,
                )

            # Approved
            rationale = (
                f"Quality gate approved proposal '{target_path}'. "
                f"Total findings: {len(findings)} (0 blocking)."
            )
            decision = AgentDecision(
                task_id=task_id,
                agent_role=AgentRole.SECURITY_AUDITOR,
                decision_type=DecisionType.APPROVE,
                is_approved=True,
                rationale=rationale,
                metadata={"findings_count": len(findings)},
            )
            logger.info(rationale, task_id=task_id, status="QUALITY_GATE_APPROVED")
            return QualityGateResult(
                target_path=target_path,
                file_type=file_type,
                is_approved=True,
                findings=findings,
                decision=decision,
                details=rationale,
            )

        except Exception as exc:
            # Fail-closed guarantee
            err_msg = f"Quality gate fail-closed on '{target_path}': {str(exc)}"
            decision = AgentDecision(
                task_id=task_id,
                agent_role=AgentRole.SECURITY_AUDITOR,
                decision_type=DecisionType.REJECT,
                is_approved=False,
                rationale=err_msg,
                metadata={"error": str(exc)},
            )
            logger.error(err_msg, task_id=task_id, status="QUALITY_GATE_ERROR")
            return QualityGateResult(
                target_path=target_path,
                file_type="unknown",
                is_approved=False,
                findings=[],
                decision=decision,
                details=err_msg,
            )

    def verify_file_on_disk(
        self,
        task_id: str,
        target_path: Path,
    ) -> QualityGateResult:
        """Verify an existing file on disk against static quality gate rules."""
        try:
            resolved, file_type = self.validate_target_path(target_path)
            if not resolved.is_file():
                raise FileNotFoundError(f"Target file does not exist: '{resolved}'")

            findings: List[Finding] = []
            if file_type == "python":
                findings = self.python_analyzer.analyze_file(resolved)
            elif file_type == "markdown":
                findings = self.markdown_validator.validate_file(resolved)

            blocking = [
                f for f in findings
                if f.severity in {FindingSeverity.MEDIUM, FindingSeverity.HIGH, FindingSeverity.CRITICAL}
            ]
            if blocking:
                rule_ids = ", ".join(f.rule_id for f in blocking)
                rationale = (
                    f"Quality gate rejected file '{target_path}' on disk due to {len(blocking)} "
                    f"blocking finding(s): {rule_ids}."
                )
                decision = AgentDecision(
                    task_id=task_id,
                    agent_role=AgentRole.SECURITY_AUDITOR,
                    decision_type=DecisionType.REJECT,
                    is_approved=False,
                    rationale=rationale,
                )
                return QualityGateResult(
                    target_path=str(target_path),
                    file_type=file_type,
                    is_approved=False,
                    findings=findings,
                    decision=decision,
                    details=rationale,
                )

            rationale = f"Quality gate approved file '{target_path}' on disk. Findings: {len(findings)}."
            decision = AgentDecision(
                task_id=task_id,
                agent_role=AgentRole.SECURITY_AUDITOR,
                decision_type=DecisionType.APPROVE,
                is_approved=True,
                rationale=rationale,
            )
            return QualityGateResult(
                target_path=str(target_path),
                file_type=file_type,
                is_approved=True,
                findings=findings,
                decision=decision,
                details=rationale,
            )

        except Exception as exc:
            err_msg = f"Quality gate fail-closed on disk file '{target_path}': {str(exc)}"
            decision = AgentDecision(
                task_id=task_id,
                agent_role=AgentRole.SECURITY_AUDITOR,
                decision_type=DecisionType.REJECT,
                is_approved=False,
                rationale=err_msg,
            )
            return QualityGateResult(
                target_path=str(target_path),
                file_type="unknown",
                is_approved=False,
                findings=[],
                decision=decision,
                details=err_msg,
            )
