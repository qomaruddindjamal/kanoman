"""Static Python AST Analyzer for Kanoman AI.

Parses Python source code into Abstract Syntax Trees (AST) using Python's standard library
ast module. Performs secure pattern detection (eval/exec, subprocess shell=True, insecure
pickle, hardcoded credentials) without executing or modifying the target codebase.
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path
from typing import Any, List, Optional, Set
from kanoman.analysis.models import AnalysisReport, Finding, FindingSeverity, RuleDefinition
from kanoman.logging.logger import get_logger

logger = get_logger("analysis.python")

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
}

PYTHON_RULES = {
    "PY_SYNTAX_ERROR": RuleDefinition(
        rule_id="PY_SYNTAX_ERROR",
        title="Python Syntax Error",
        severity=FindingSeverity.HIGH,
        description="The source file contains invalid Python syntax and cannot be parsed.",
        recommendation="Correct the syntax error according to Python grammar.",
    ),
    "PY_EVAL_EXEC": RuleDefinition(
        rule_id="PY_EVAL_EXEC",
        title="Dynamic Code Execution (eval/exec)",
        severity=FindingSeverity.HIGH,
        description="Calls to eval() or exec() allow arbitrary code execution vulnerabilities.",
        recommendation="Replace eval()/exec() with safe dispatch tables or ast.literal_eval.",
    ),
    "PY_SUBPROCESS_SHELL": RuleDefinition(
        rule_id="PY_SUBPROCESS_SHELL",
        title="Subprocess Insecure Shell Execution",
        severity=FindingSeverity.HIGH,
        description="Calling subprocess functions with shell=True exposes the application to OS command injection (CWE-78).",
        recommendation="Pass command arguments as a list of strings with shell=False.",
    ),
    "PY_INSECURE_PICKLE": RuleDefinition(
        rule_id="PY_INSECURE_PICKLE",
        title="Insecure Deserialization via Pickle",
        severity=FindingSeverity.MEDIUM,
        description="Unpickling data from untrusted sources can result in remote code execution (CWE-502).",
        recommendation="Use safe structured data formats such as JSON or Pydantic models.",
    ),
    "PY_HARDCODED_SECRET": RuleDefinition(
        rule_id="PY_HARDCODED_SECRET",
        title="Potential Hardcoded Secret",
        severity=FindingSeverity.HIGH,
        description="Hardcoded API keys, tokens, or passwords detected in source assignment.",
        recommendation="Load secrets from environment variables or secure vault storage.",
    ),
    "PY_FILE_READ_ERROR": RuleDefinition(
        rule_id="PY_FILE_READ_ERROR",
        title="File Read Error",
        severity=FindingSeverity.MEDIUM,
        description="Unable to read the target file due to I/O or encoding errors.",
        recommendation="Ensure the file exists, has valid permissions, and uses UTF-8 encoding.",
    ),
}


class _SecurityASTVisitor(ast.NodeVisitor):
    """Internal AST visitor inspecting nodes against defined security heuristics."""

    def __init__(self, file_path_str: str) -> None:
        self.file_path_str = file_path_str
        self.findings: List[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check 1: eval() or exec()
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in {"eval", "exec"}:
            self.findings.append(
                Finding(
                    rule_id="PY_EVAL_EXEC",
                    severity=FindingSeverity.HIGH,
                    message=f"Dynamic code execution detected via call to '{func_name}()'.",
                    file_path=self.file_path_str,
                    line=node.lineno,
                    column=node.col_offset,
                    recommendation=PYTHON_RULES["PY_EVAL_EXEC"].recommendation,
                )
            )

        # Check 2: subprocess with shell=True
        is_subprocess = False
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                is_subprocess = True
            elif node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}:
                is_subprocess = True
        elif isinstance(node.func, ast.Name) and node.func.id in {"system", "popen"}:
            is_subprocess = True

        if is_subprocess:
            for kw in node.keywords:
                if kw.arg == "shell":
                    # Check if value evaluates to True
                    if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.findings.append(
                            Finding(
                                rule_id="PY_SUBPROCESS_SHELL",
                                severity=FindingSeverity.HIGH,
                                message="Subprocess invocation with shell=True creates OS command injection risk (CWE-78).",
                                file_path=self.file_path_str,
                                line=node.lineno,
                                column=node.col_offset,
                                recommendation=PYTHON_RULES["PY_SUBPROCESS_SHELL"].recommendation,
                            )
                        )

        # Check 3: pickle.load / pickle.loads
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pickle":
                if node.func.attr in {"load", "loads"}:
                    self.findings.append(
                        Finding(
                            rule_id="PY_INSECURE_PICKLE",
                            severity=FindingSeverity.MEDIUM,
                            message=f"Insecure deserialization detected via 'pickle.{node.func.attr}()'.",
                            file_path=self.file_path_str,
                            line=node.lineno,
                            column=node.col_offset,
                            recommendation=PYTHON_RULES["PY_INSECURE_PICKLE"].recommendation,
                        )
                    )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check 4: Potential hardcoded secret in assignments
        suspicious_names = re.compile(r"^(api_key|apikey|secret|password|auth_token|access_token|private_key)$", re.I)
        for target in node.targets:
            target_name = ""
            if isinstance(target, ast.Name):
                target_name = target.id

            if target_name and suspicious_names.match(target_name):
                # Inspect assigned value
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    val = node.value.value.strip()
                    # Filter placeholders and dummy tokens
                    ignored_values = {"", "none", "dummy", "test", "placeholder", "changeme", "***redacted***"}
                    if len(val) >= 12 and val.lower() not in ignored_values and not val.startswith("${"):
                        self.findings.append(
                            Finding(
                                rule_id="PY_HARDCODED_SECRET",
                                severity=FindingSeverity.HIGH,
                                message=f"Potential hardcoded secret assigned to variable '{target_name}'.",
                                file_path=self.file_path_str,
                                line=node.lineno,
                                column=node.col_offset,
                                recommendation=PYTHON_RULES["PY_HARDCODED_SECRET"].recommendation,
                            )
                        )

        self.generic_visit(node)


class PythonASTAnalyzer:
    """Performs static code analysis over Python sources using standard library AST."""

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

    def analyze_source(self, code: str, file_path_str: str = "<memory>") -> List[Finding]:
        """Parse and analyze in-memory Python source code."""
        try:
            tree = ast.parse(code, filename=file_path_str)
        except SyntaxError as syn_err:
            return [
                Finding(
                    rule_id="PY_SYNTAX_ERROR",
                    severity=FindingSeverity.HIGH,
                    message=f"SyntaxError: {syn_err.msg}",
                    file_path=file_path_str,
                    line=syn_err.lineno,
                    column=syn_err.offset,
                    recommendation=PYTHON_RULES["PY_SYNTAX_ERROR"].recommendation,
                )
            ]

        visitor = _SecurityASTVisitor(file_path_str)
        visitor.visit(tree)
        return visitor.findings

    def analyze_file(self, file_path: Path) -> List[Finding]:
        """Analyze a single Python file on disk."""
        resolved = self.validate_path(file_path)

        if not resolved.is_file():
            return [
                Finding(
                    rule_id="PY_FILE_READ_ERROR",
                    severity=FindingSeverity.MEDIUM,
                    message=f"File not found: '{file_path}'",
                    file_path=str(file_path),
                    recommendation="Verify that the target file exists.",
                )
            ]

        try:
            code = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                code = resolved.read_text(encoding="latin-1")
            except Exception as e:
                return [
                    Finding(
                        rule_id="PY_FILE_READ_ERROR",
                        severity=FindingSeverity.MEDIUM,
                        message=f"Encoding error reading file: {str(e)}",
                        file_path=str(file_path),
                        recommendation="Save file with standard UTF-8 encoding.",
                    )
                ]
        except Exception as e:
            return [
                Finding(
                    rule_id="PY_FILE_READ_ERROR",
                    severity=FindingSeverity.MEDIUM,
                    message=f"I/O error reading file: {str(e)}",
                    file_path=str(file_path),
                    recommendation="Check file read permissions.",
                )
            ]

        # Use relative path in findings for clean portability
        try:
            rel_str = str(resolved.relative_to(self.workspace_root))
        except ValueError:
            rel_str = str(resolved)

        return self.analyze_source(code, file_path_str=rel_str)

    def analyze_directory(self, target_dir: Optional[Path] = None) -> AnalysisReport:
        """Recursively scan all Python files within target directory."""
        dir_to_scan = self.validate_path(target_dir or self.workspace_root)
        start_t = time.time()
        findings: List[Finding] = []
        files_scanned = 0

        for path in dir_to_scan.rglob("*.py"):
            # Check exclusions
            if any(part in self.excluded_dirs for part in path.parts):
                continue
            if path.is_file():
                files_scanned += 1
                findings.extend(self.analyze_file(path))

        elapsed_ms = (time.time() - start_t) * 1000.0

        return AnalysisReport(
            analyzer_name="PythonASTAnalyzer",
            workspace_root=str(self.workspace_root),
            files_scanned=files_scanned,
            findings=findings,
            duration_ms=elapsed_ms,
        )
