"""Data models for static analysis and validation findings."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleDefinition(BaseModel):
    """Specification of an analysis rule."""

    rule_id: str
    title: str
    severity: FindingSeverity
    description: str
    recommendation: str


class Finding(BaseModel):
    """Structured report item representing a single detection or warning."""

    rule_id: str = Field(..., description="Stable rule identifier.")
    severity: FindingSeverity = Field(..., description="Severity level of the finding.")
    message: str = Field(..., description="Concise explanation of the detected issue.")
    file_path: str = Field(..., description="Relative or normalized path to the inspected file.")
    line: Optional[int] = Field(default=None, description="Line number (1-indexed).")
    column: Optional[int] = Field(default=None, description="Column offset (0-indexed).")
    recommendation: Optional[str] = Field(default=None, description="Suggested remediation.")
    confidence: str = Field(default="HIGH", description="Detection confidence (LOW, MEDIUM, HIGH).")


class AnalysisReport(BaseModel):
    """Aggregated output of a static analysis or validation run."""

    analyzer_name: str
    workspace_root: str
    files_scanned: int = 0
    findings: List[Finding] = Field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def is_clean(self) -> bool:
        """Returns True if no findings were reported."""
        return len(self.findings) == 0

    @property
    def has_high_or_critical(self) -> bool:
        """Returns True if any HIGH or CRITICAL severity findings are present."""
        return any(f.severity in {FindingSeverity.HIGH, FindingSeverity.CRITICAL} for f in self.findings)

    @property
    def summary_by_severity(self) -> Dict[str, int]:
        """Group count of findings by severity."""
        counts = {sev.value: 0 for sev in FindingSeverity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts
