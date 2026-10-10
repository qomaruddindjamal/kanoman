"""Unit and integration tests for static code analysis and markdown validation."""

import json
from pathlib import Path
import pytest

from kanoman.analysis.models import FindingSeverity, AnalysisReport
from kanoman.analysis.python_analyzer import PythonASTAnalyzer
from kanoman.analysis.markdown_validator import MarkdownValidator
from kanoman.cli.main import main as cli_main
from kanoman.core.models import Task, TaskPriority, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# =====================================================================
# Python AST Analyzer Tests
# =====================================================================

def test_python_analyzer_clean_code(temp_workspace: Path):
    clean_file = temp_workspace / "clean.py"
    clean_file.write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\nresult = add(2, 3)\n",
        encoding="utf-8",
    )
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(clean_file)
    assert len(findings) == 0


def test_python_analyzer_syntax_error(temp_workspace: Path):
    bad_file = temp_workspace / "bad_syntax.py"
    bad_file.write_text("def broken_syntax(\n", encoding="utf-8")
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(bad_file)
    assert len(findings) == 1
    assert findings[0].rule_id == "PY_SYNTAX_ERROR"
    assert findings[0].severity == FindingSeverity.HIGH


def test_python_analyzer_eval_exec(temp_workspace: Path):
    eval_file = temp_workspace / "eval_code.py"
    eval_file.write_text(
        "user_input = '__import__(\"os\").system(\"calc\")'\neval(user_input)\nexec('x = 1')\n",
        encoding="utf-8",
    )
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(eval_file)
    assert len(findings) == 2
    rule_ids = [f.rule_id for f in findings]
    assert rule_ids == ["PY_EVAL_EXEC", "PY_EVAL_EXEC"]


def test_python_analyzer_subprocess_shell(temp_workspace: Path):
    sub_file = temp_workspace / "sub_call.py"
    sub_file.write_text(
        "import subprocess\nsubprocess.run('ls -la', shell=True)\n",
        encoding="utf-8",
    )
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(sub_file)
    assert len(findings) == 1
    assert findings[0].rule_id == "PY_SUBPROCESS_SHELL"
    assert findings[0].severity == FindingSeverity.HIGH


def test_python_analyzer_insecure_pickle(temp_workspace: Path):
    pickle_file = temp_workspace / "unpickle.py"
    pickle_file.write_text(
        "import pickle\ndata = b'cos\\nsystem\\n(S\"ls\"\\ntR.'\npickle.loads(data)\n",
        encoding="utf-8",
    )
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(pickle_file)
    assert len(findings) == 1
    assert findings[0].rule_id == "PY_INSECURE_PICKLE"
    assert findings[0].severity == FindingSeverity.MEDIUM


def test_python_analyzer_hardcoded_secret(temp_workspace: Path):
    secret_file = temp_workspace / "secrets.py"
    secret_file.write_text(
        "api_key = 'AIzaSyD-SecretToken123456789'\nnormal_var = 'hello world'\n",
        encoding="utf-8",
    )
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(secret_file)
    assert len(findings) == 1
    assert findings[0].rule_id == "PY_HARDCODED_SECRET"
    assert findings[0].severity == FindingSeverity.HIGH


def test_python_analyzer_path_traversal_protection(temp_workspace: Path):
    outside_file = temp_workspace.parent / "outside.py"
    outside_file.write_text("print('outside')", encoding="utf-8")
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    with pytest.raises(ValueError, match="Path traversal detected"):
        analyzer.analyze_file(outside_file)


def test_python_analyzer_missing_file(temp_workspace: Path):
    missing_file = temp_workspace / "does_not_exist.py"
    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    findings = analyzer.analyze_file(missing_file)
    assert len(findings) == 1
    assert findings[0].rule_id == "PY_FILE_READ_ERROR"


def test_python_analyzer_directory_scan(temp_workspace: Path):
    (temp_workspace / "src").mkdir()
    (temp_workspace / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (temp_workspace / ".git").mkdir()
    (temp_workspace / ".git" / "ignored.py").write_text("eval('1')", encoding="utf-8")

    analyzer = PythonASTAnalyzer(workspace_root=temp_workspace)
    report = analyzer.analyze_directory()
    assert report.files_scanned == 1
    assert report.is_clean is True


# =====================================================================
# Markdown Validator Tests
# =====================================================================

def test_markdown_validator_clean(temp_workspace: Path):
    doc = temp_workspace / "README.md"
    doc.write_text(
        "# Title\n\nThis is clean markdown.\n\n- [ ] Task 1\n- [x] Task 2\n\n```python\nprint(1)\n```\n",
        encoding="utf-8",
    )
    validator = MarkdownValidator(workspace_root=temp_workspace)
    findings = validator.validate_file(doc)
    assert len(findings) == 0


def test_markdown_validator_empty_file(temp_workspace: Path):
    empty_doc = temp_workspace / "EMPTY.md"
    empty_doc.write_text("   \n\n", encoding="utf-8")
    validator = MarkdownValidator(workspace_root=temp_workspace)
    findings = validator.validate_file(empty_doc)
    assert len(findings) == 1
    assert findings[0].rule_id == "MD_EMPTY_FILE"


def test_markdown_validator_empty_heading(temp_workspace: Path):
    doc = temp_workspace / "bad_heading.md"
    doc.write_text("# \n## Valid Heading\n", encoding="utf-8")
    validator = MarkdownValidator(workspace_root=temp_workspace)
    findings = validator.validate_file(doc)
    assert len(findings) == 1
    assert findings[0].rule_id == "MD_EMPTY_HEADING"


def test_markdown_validator_unclosed_fence(temp_workspace: Path):
    doc = temp_workspace / "unclosed.md"
    doc.write_text("# Doc\n\n```python\nprint('hello')\n", encoding="utf-8")
    validator = MarkdownValidator(workspace_root=temp_workspace)
    findings = validator.validate_file(doc)
    assert len(findings) == 1
    assert findings[0].rule_id == "MD_UNCLOSED_FENCE"


def test_markdown_validator_broken_link_and_missing_local_ref(temp_workspace: Path):
    doc = temp_workspace / "links.md"
    doc.write_text(
        "# Links\n\n[Empty link]()\n[Missing File](non_existent.md)\n[Valid External](https://example.com)\n",
        encoding="utf-8",
    )
    validator = MarkdownValidator(workspace_root=temp_workspace)
    findings = validator.validate_file(doc)
    rule_ids = [f.rule_id for f in findings]
    assert "MD_BROKEN_LINK" in rule_ids
    assert "MD_MISSING_LOCAL_REF" in rule_ids


def test_markdown_validator_malformed_checklist(temp_workspace: Path):
    doc = temp_workspace / "checklists.md"
    doc.write_text(
        "# Checklist\n\n- [?] Invalid check\n- [x]Valid no space\n",
        encoding="utf-8",
    )
    validator = MarkdownValidator(workspace_root=temp_workspace)
    findings = validator.validate_file(doc)
    assert len(findings) == 2
    for f in findings:
        assert f.rule_id == "MD_MALFORMED_CHECKLIST"


def test_markdown_validator_path_traversal(temp_workspace: Path):
    outside = temp_workspace.parent / "doc.md"
    outside.write_text("# Outside", encoding="utf-8")
    validator = MarkdownValidator(workspace_root=temp_workspace)
    with pytest.raises(ValueError, match="Path traversal detected"):
        validator.validate_file(outside)


# =====================================================================
# CLI Integration Tests
# =====================================================================

def test_cli_analyze_python_clean(temp_workspace: Path, capsys):
    clean_py = temp_workspace / "clean.py"
    clean_py.write_text("a = 1 + 2\n", encoding="utf-8")
    exit_code = cli_main(["analyze", "python", str(clean_py), "--root", str(temp_workspace)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "All files passed analysis cleanly." in captured.out


def test_cli_analyze_python_vulnerable(temp_workspace: Path, capsys):
    vuln_py = temp_workspace / "vuln.py"
    vuln_py.write_text("eval('1+1')\n", encoding="utf-8")
    exit_code = cli_main(["analyze", "python", str(vuln_py), "--root", str(temp_workspace)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "PY_EVAL_EXEC" in captured.out


def test_cli_analyze_markdown_json(temp_workspace: Path, capsys):
    doc = temp_workspace / "doc.md"
    doc.write_text("# Hello World\n", encoding="utf-8")
    exit_code = cli_main(["analyze", "markdown", str(doc), "--root", str(temp_workspace), "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    data = json.loads(captured.out)
    assert data["analyzer_name"] == "MarkdownValidator"
    assert data["files_scanned"] == 1


# =====================================================================
# Orchestrator Task Execution Tests
# =====================================================================

def test_orchestrator_analyze_python_task(temp_workspace: Path):
    src_file = temp_workspace / "test_module.py"
    src_file.write_text("x = 42\n", encoding="utf-8")

    from kanoman.config.settings import KanomanConfig
    config = KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
    )
    orchestrator = TaskOrchestrator(config=config)
    task = Task(
        title="Analyze Python Code",
        description="Run AST security inspection",
        priority=TaskPriority.HIGH,
        metadata={"target_path": str(src_file)},
    )
    result = orchestrator.execute_task(task, task_type="analyze_python")
    assert result.status == TaskStatus.COMPLETED
    assert "Python AST analysis completed" in result.result_summary
    assert result.checkpoint_id is not None


def test_orchestrator_validate_markdown_task(temp_workspace: Path):
    doc_file = temp_workspace / "README.md"
    doc_file.write_text("# Project Documentation\n\nOverview content.", encoding="utf-8")

    from kanoman.config.settings import KanomanConfig
    config = KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
    )
    orchestrator = TaskOrchestrator(config=config)
    task = Task(
        title="Validate Markdown Docs",
        description="Run structural markdown validation",
        priority=TaskPriority.MEDIUM,
        metadata={"target_path": str(doc_file)},
    )
    result = orchestrator.execute_task(task, task_type="validate_markdown")
    assert result.status == TaskStatus.COMPLETED
    assert "Markdown validation completed" in result.result_summary
    assert result.checkpoint_id is not None
