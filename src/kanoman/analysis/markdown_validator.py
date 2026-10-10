"""Static Markdown Validator for Kanoman AI.

Validates Markdown documentation files for structural integrity, syntax correctness,
broken local file references, empty headings, malformed checklists, and unclosed code fences
without executing any external processes or adding third-party dependencies.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional, Set
from kanoman.analysis.models import AnalysisReport, Finding, FindingSeverity, RuleDefinition
from kanoman.logging.logger import get_logger

logger = get_logger("analysis.markdown")

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".kanoman_checkpoints",
    "dist",
    "build",
    "site-packages",
    "node_modules",
}

MARKDOWN_RULES = {
    "MD_EMPTY_FILE": RuleDefinition(
        rule_id="MD_EMPTY_FILE",
        title="Empty Markdown File",
        severity=FindingSeverity.LOW,
        description="The Markdown document is completely empty or contains only whitespace.",
        recommendation="Add documentation content or remove the unnecessary empty file.",
    ),
    "MD_EMPTY_HEADING": RuleDefinition(
        rule_id="MD_EMPTY_HEADING",
        title="Empty Heading",
        severity=FindingSeverity.LOW,
        description="A heading marker (#) is present without any heading title text.",
        recommendation="Provide descriptive text for the heading or remove the orphan marker.",
    ),
    "MD_UNCLOSED_FENCE": RuleDefinition(
        rule_id="MD_UNCLOSED_FENCE",
        title="Unclosed Code Block Fence",
        severity=FindingSeverity.MEDIUM,
        description="A code block was opened with backticks or tildes but never closed before end-of-file.",
        recommendation="Close the code block fence with matching backticks or tildes.",
    ),
    "MD_BROKEN_LINK": RuleDefinition(
        rule_id="MD_BROKEN_LINK",
        title="Broken or Malformed Link Syntax",
        severity=FindingSeverity.MEDIUM,
        description="A Markdown link contains empty targets or malformed syntax.",
        recommendation="Provide a valid target URL or path in [text](url).",
    ),
    "MD_MALFORMED_CHECKLIST": RuleDefinition(
        rule_id="MD_MALFORMED_CHECKLIST",
        title="Malformed Checklist Item",
        severity=FindingSeverity.LOW,
        description="Checklist syntax is malformed (e.g. missing space, invalid check character).",
        recommendation="Use standard checklist syntax: '- [ ] item' or '- [x] item'.",
    ),
    "MD_MISSING_LOCAL_REF": RuleDefinition(
        rule_id="MD_MISSING_LOCAL_REF",
        title="Missing Local File Reference",
        severity=FindingSeverity.MEDIUM,
        description="A relative link points to a local file that does not exist on disk.",
        recommendation="Verify and correct the relative file path destination.",
    ),
    "MD_FILE_READ_ERROR": RuleDefinition(
        rule_id="MD_FILE_READ_ERROR",
        title="File Read Error",
        severity=FindingSeverity.MEDIUM,
        description="Unable to read the target file due to I/O or encoding errors.",
        recommendation="Ensure the file exists, has valid permissions, and uses UTF-8 encoding.",
    ),
}

# Regex patterns
RE_HEADING_EMPTY = re.compile(r"^\s*#{1,6}\s*$")
RE_CODE_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
RE_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
RE_MALFORMED_CHECKLIST = re.compile(r"^\s*[-*+]\s*\[([^ xX]| {2,})\](?:\s.*)?$")
RE_CHECKLIST_NO_SPACE = re.compile(r"^\s*[-*+]\s*\[([ xX])\][^\s]")


class MarkdownValidator:
    """Performs structural and syntax validation on Markdown files."""

    def __init__(
        self,
        workspace_root: Path,
        excluded_dirs: Optional[Set[str]] = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.excluded_dirs = excluded_dirs or DEFAULT_EXCLUDED_DIRS

    def validate_path(self, target_path: Path) -> Path:
        """Ensure path is within the permitted workspace root, mitigating path traversal."""
        resolved = target_path.resolve()
        if self.workspace_root not in resolved.parents and resolved != self.workspace_root:
            raise ValueError(
                f"Path traversal detected: target '{target_path}' resolves to '{resolved}' "
                f"which is outside authorized workspace root '{self.workspace_root}'"
            )
        return resolved

    def validate_content(
        self,
        content: str,
        file_path_str: str = "<memory>",
        base_dir: Optional[Path] = None,
    ) -> List[Finding]:
        """Validate in-memory Markdown content against structural and syntax rules."""
        findings: List[Finding] = []

        if not content.strip():
            findings.append(
                Finding(
                    rule_id="MD_EMPTY_FILE",
                    severity=FindingSeverity.LOW,
                    message="Markdown file is empty or contains only whitespace.",
                    file_path=file_path_str,
                    line=1,
                    recommendation=MARKDOWN_RULES["MD_EMPTY_FILE"].recommendation,
                )
            )
            return findings

        lines = content.splitlines()
        in_fence = False
        fence_marker = ""
        fence_start_line = 0

        for line_idx, line in enumerate(lines, start=1):
            # Check for code fence start/end
            fence_match = RE_CODE_FENCE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                marker_char = marker[0]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker_char
                    fence_start_line = line_idx
                    continue
                else:
                    if marker_char == fence_marker:
                        in_fence = False
                        fence_marker = ""
                        continue

            # If inside code fence, skip structural content checks
            if in_fence:
                continue

            # Check for empty heading
            if RE_HEADING_EMPTY.match(line):
                findings.append(
                    Finding(
                        rule_id="MD_EMPTY_HEADING",
                        severity=FindingSeverity.LOW,
                        message="Empty heading detected with no title text.",
                        file_path=file_path_str,
                        line=line_idx,
                        recommendation=MARKDOWN_RULES["MD_EMPTY_HEADING"].recommendation,
                    )
                )

            # Check for malformed checklist
            if RE_MALFORMED_CHECKLIST.match(line):
                findings.append(
                    Finding(
                        rule_id="MD_MALFORMED_CHECKLIST",
                        severity=FindingSeverity.LOW,
                        message="Malformed checklist checkbox: must contain exactly one space or 'x'.",
                        file_path=file_path_str,
                        line=line_idx,
                        recommendation=MARKDOWN_RULES["MD_MALFORMED_CHECKLIST"].recommendation,
                    )
                )
            elif RE_CHECKLIST_NO_SPACE.match(line):
                findings.append(
                    Finding(
                        rule_id="MD_MALFORMED_CHECKLIST",
                        severity=FindingSeverity.LOW,
                        message="Malformed checklist: missing space after checkbox bracket.",
                        file_path=file_path_str,
                        line=line_idx,
                        recommendation=MARKDOWN_RULES["MD_MALFORMED_CHECKLIST"].recommendation,
                    )
                )

            # Check for link issues
            for match in RE_LINK.finditer(line):
                text = match.group(1)
                href = match.group(2).strip()

                if not href:
                    findings.append(
                        Finding(
                            rule_id="MD_BROKEN_LINK",
                            severity=FindingSeverity.MEDIUM,
                            message=f"Markdown link '[{text}]()' has an empty target URL/path.",
                            file_path=file_path_str,
                            line=line_idx,
                            recommendation=MARKDOWN_RULES["MD_BROKEN_LINK"].recommendation,
                        )
                    )
                    continue

                # Local file reference check
                # Skip external protocols, mailto, and in-page anchor links
                if (
                    href.startswith("http://")
                    or href.startswith("https://")
                    or href.startswith("mailto:")
                    or href.startswith("ftp://")
                    or href.startswith("#")
                ):
                    continue

                # Strip anchor fragment or query params
                href_clean = href.split("#")[0].split("?")[0].strip()
                if not href_clean:
                    continue

                if base_dir is not None:
                    # Check relative to base_dir or workspace_root
                    candidate_1 = (base_dir / href_clean).resolve()
                    candidate_2 = (self.workspace_root / href_clean.lstrip("/\\")).resolve()

                    if not candidate_1.exists() and not candidate_2.exists():
                        findings.append(
                            Finding(
                                rule_id="MD_MISSING_LOCAL_REF",
                                severity=FindingSeverity.MEDIUM,
                                message=f"Local reference target '{href_clean}' does not exist on disk.",
                                file_path=file_path_str,
                                line=line_idx,
                                recommendation=MARKDOWN_RULES["MD_MISSING_LOCAL_REF"].recommendation,
                            )
                        )

        # Check if code fence left unclosed at end of file
        if in_fence:
            findings.append(
                Finding(
                    rule_id="MD_UNCLOSED_FENCE",
                    severity=FindingSeverity.MEDIUM,
                    message="Code block was opened but never closed before end-of-file.",
                    file_path=file_path_str,
                    line=fence_start_line,
                    recommendation=MARKDOWN_RULES["MD_UNCLOSED_FENCE"].recommendation,
                )
            )

        return findings

    def validate_file(self, file_path: Path) -> List[Finding]:
        """Validate a single Markdown file on disk."""
        resolved = self.validate_path(file_path)

        if not resolved.is_file():
            return [
                Finding(
                    rule_id="MD_FILE_READ_ERROR",
                    severity=FindingSeverity.MEDIUM,
                    message=f"File not found: '{file_path}'",
                    file_path=str(file_path),
                    recommendation="Verify that the target file exists.",
                )
            ]

        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = resolved.read_text(encoding="latin-1")
            except Exception as e:
                return [
                    Finding(
                        rule_id="MD_FILE_READ_ERROR",
                        severity=FindingSeverity.MEDIUM,
                        message=f"Encoding error reading file: {str(e)}",
                        file_path=str(file_path),
                        recommendation="Save file with standard UTF-8 encoding.",
                    )
                ]
        except Exception as e:
            return [
                Finding(
                    rule_id="MD_FILE_READ_ERROR",
                    severity=FindingSeverity.MEDIUM,
                    message=f"I/O error reading file: {str(e)}",
                    file_path=str(file_path),
                    recommendation="Check file read permissions.",
                )
            ]

        try:
            rel_str = str(resolved.relative_to(self.workspace_root))
        except ValueError:
            rel_str = str(resolved)

        return self.validate_content(content, file_path_str=rel_str, base_dir=resolved.parent)

    def validate_directory(self, target_dir: Optional[Path] = None) -> AnalysisReport:
        """Recursively scan and validate all Markdown files within target directory."""
        dir_to_scan = self.validate_path(target_dir or self.workspace_root)
        start_t = time.time()
        findings: List[Finding] = []
        files_scanned = 0

        for path in dir_to_scan.rglob("*.md"):
            if any(part in self.excluded_dirs for part in path.parts):
                continue
            if path.is_file():
                files_scanned += 1
                findings.extend(self.validate_file(path))

        elapsed_ms = (time.time() - start_t) * 1000.0

        return AnalysisReport(
            analyzer_name="MarkdownValidator",
            workspace_root=str(self.workspace_root),
            files_scanned=files_scanned,
            findings=findings,
            duration_ms=elapsed_ms,
        )
