"""CLI Entrypoint for Kanoman AI.

Provides structured, safe subcommands to operate the Kanoman Core:
- kanoman status
- kanoman config
- kanoman project list / add
- kanoman task run
- kanoman checkpoint list / show
- kanoman git inspect / dry-run
- kanoman test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import get_config
from kanoman.core.models import Project, Task, TaskPriority
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry
from kanoman.git.controller import GitController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kanoman",
        description="Kanoman AI — Modular, Secure AI Development Orchestrator CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Subcommand: status
    subparsers.add_parser("status", help="Display overall Kanoman status and telemetry.")

    # Subcommand: config
    subparsers.add_parser("config", help="Validate and display active configuration (masked).")

    # Subcommand: project
    proj_parser = subparsers.add_parser("project", help="Manage registered projects.")
    proj_subs = proj_parser.add_subparsers(dest="proj_action")
    proj_subs.add_parser("list", help="List all registered projects.")
    add_p = proj_subs.add_parser("add", help="Register a project.")
    add_p.add_argument("--id", required=True, help="Unique project identifier.")
    add_p.add_argument("--name", required=True, help="Human-readable project name.")
    add_p.add_argument("--root", required=True, help="Workspace root directory path.")
    add_p.add_argument("--remote", required=True, help="Authorized remote URL.")

    # Subcommand: task
    task_parser = subparsers.add_parser("task", help="Execute tasks.")
    task_subs = task_parser.add_subparsers(dest="task_action")
    run_t = task_subs.add_parser("run", help="Run a task through the orchestrator.")
    run_t.add_argument("--project-id", default=None, help="Target project identifier registered with Kanoman.")
    run_t.add_argument("--title", required=True, help="Task title.")
    run_t.add_argument("--desc", required=True, help="Task description.")
    run_t.add_argument("--type", default="ping", help="Task type (default: ping).")
    run_t.add_argument("--priority", default="MEDIUM", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    run_t.add_argument("--provider", default=None, choices=["mock", "gemini"], help="AI provider.")
    run_t.add_argument("--use-specialists", action="store_true", help="Enable specialist runners.")

    # Subcommand: checkpoint
    chk_parser = subparsers.add_parser("checkpoint", help="Inspect recovery checkpoints.")
    chk_subs = chk_parser.add_subparsers(dest="chk_action")
    chk_subs.add_parser("list", help="List recent checkpoints.")
    show_c = chk_subs.add_parser("show", help="Display details for a specific checkpoint.")
    show_c.add_argument("id", help="Checkpoint ID.")

    # Subcommand: git
    git_parser = subparsers.add_parser("git", help="Inspect and simulate safe Git operations.")
    git_subs = git_parser.add_subparsers(dest="git_action")
    git_subs.add_parser("inspect", help="Inspect current repository status.")
    dry_g = git_subs.add_parser("dry-run", help="Simulate a commit operation without mutating.")
    dry_g.add_argument("--files", nargs="+", required=True, help="Files to simulate staging.")
    dry_g.add_argument("-m", "--message", required=True, help="Commit message.")

    # Subcommand: analyze
    analyze_parser = subparsers.add_parser("analyze", help="Perform automated static code and document analysis.")
    analyze_subs = analyze_parser.add_subparsers(dest="analyze_action")

    py_p = analyze_subs.add_parser("python", help="Analyze Python files via AST security visitor.")
    py_p.add_argument("path", nargs="?", default=".", help="Target file or directory path (default: current directory).")
    py_p.add_argument("--root", default=None, help="Authorized workspace root (default: config.workspace_root).")
    py_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text).")

    md_p = analyze_subs.add_parser("markdown", help="Validate Markdown files for structure and links.")
    md_p.add_argument("path", nargs="?", default=".", help="Target file or directory path (default: current directory).")
    md_p.add_argument("--root", default=None, help="Authorized workspace root (default: config.workspace_root).")
    md_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text).")

    # Subcommand: agent
    agent_parser = subparsers.add_parser("agent", help="Coordinate multi-agent workflows.")
    agent_subs = agent_parser.add_subparsers(dest="agent_action")
    coord_p = agent_subs.add_parser("coordinate", help="Coordinate multi-agent workflow for a task.")
    coord_p.add_argument("--project-id", default=None, help="Target project identifier registered with Kanoman.")
    coord_p.add_argument("--title", required=True, help="Task title (3-200 chars).")
    coord_p.add_argument("--desc", required=True, help="Task description (5-4000 chars).")
    coord_p.add_argument("--priority", default="MEDIUM", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    coord_p.add_argument("--provider", default=None, choices=["mock", "gemini"], help="AI provider.")
    coord_p.add_argument("--max-iterations", type=int, default=5, help="Max iterations (1-20).")
    coord_p.add_argument("--token-budget", type=int, default=50000, help="Max token budget (100-500000).")
    coord_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    coord_p.add_argument("--no-specialists", action="store_true", help="Disable specialist persona runners.")

    # Subcommand: test
    subparsers.add_parser("test", help="Execute test suite via pytest.")

    return parser


def main(
    args: list[str] | None = None,
    config: KanomanConfig | None = None,
    orchestrator: TaskOrchestrator | None = None,
) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    config = config or get_config()
    shared_registry = ProjectRegistry(storage_file=config.workspace_root / ".kanoman_projects.json")
    active_orch = orchestrator or TaskOrchestrator(config=config, registry=shared_registry)

    if not parsed.subcommand:
        parser.print_help()
        return 0

    if parsed.subcommand == "status":
        recovery = RecoveryEngine(config.checkpoint_dir)
        latest_chk = recovery.get_latest_checkpoint()
        print("=== Kanoman AI System Status ===")
        print(f"Environment:       {config.env.value}")
        print(f"Workspace Root:    {config.workspace_root}")
        print(f"Git Dry Run:       {config.git_dry_run}")
        print(f"Allowed Remote:    {config.git_allowed_remote}")
        print(f"Default Provider:  {config.default_ai_provider}")
        print(f"Latest Checkpoint: {latest_chk.checkpoint_id if latest_chk else 'None'}")
        return 0

    elif parsed.subcommand == "config":
        print(json.dumps(config.model_dump_safe(), indent=2))
        return 0

    elif parsed.subcommand == "project":
        registry = shared_registry
        if parsed.proj_action == "list":
            projects = registry.list_projects()
            print(f"Registered Projects ({len(projects)}):")
            for p in projects:
                print(f" - [{p.project_id}] {p.name} ({p.workspace_root})")
            return 0
        elif parsed.proj_action == "add":
            try:
                proj = Project(
                    project_id=parsed.id,
                    name=parsed.name,
                    workspace_root=Path(parsed.root),
                    allowed_remote_url=parsed.remote,
                )
                registry.register_project(proj)
                print(f"Successfully registered project '{proj.project_id}'")
                return 0
            except Exception as e:
                print(f"Error registering project: {e}", file=sys.stderr)
                return 1

    elif parsed.subcommand == "task":
        if parsed.task_action == "run":
            metadata = {}
            if getattr(parsed, "use_specialists", False):
                metadata["use_specialists"] = True
            if getattr(parsed, "provider", None):
                metadata["provider"] = parsed.provider
            proj_id = getattr(parsed, "project_id", None)
            task = Task(
                title=parsed.title,
                description=parsed.desc,
                project_id=proj_id,
                priority=TaskPriority[parsed.priority],
                metadata=metadata,
            )
            finished = active_orch.execute_task(task, task_type=parsed.type)
            print(f"Task ID:     {finished.task_id}")
            print(f"Status:      {finished.status.value}")
            print(f"Result:      {finished.result_summary}")
            print(f"Checkpoint:  {finished.checkpoint_id}")
            return 0 if finished.status.value == "COMPLETED" else 1

    elif parsed.subcommand == "checkpoint":
        recovery = RecoveryEngine(config.checkpoint_dir)
        if parsed.chk_action == "list":
            files = list(config.checkpoint_dir.glob("chk_*.json"))
            print(f"Found {len(files)} checkpoint(s):")
            for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                print(f" - {f.stem}")
            return 0
        elif parsed.chk_action == "show":
            try:
                chk = recovery.load_checkpoint(parsed.id)
                print(chk.model_dump_json(indent=2))
                return 0
            except Exception as e:
                print(f"Error loading checkpoint: {e}", file=sys.stderr)
                return 1

    elif parsed.subcommand == "git":
        ctrl = GitController(
            workspace_root=config.workspace_root,
            allowed_remote=config.git_allowed_remote,
            allowed_branches=config.git_allowed_branches,
            config=config,
        )
        if parsed.git_action == "inspect":
            try:
                status = ctrl.inspect()
                print(f"Branch:         {status.current_branch}")
                print(f"Clean Tree:     {status.is_clean}")
                print(f"Staged ({len(status.staged_files)}):    {status.staged_files}")
                print(f"Unstaged ({len(status.unstaged_files)}):  {status.unstaged_files}")
                print(f"Untracked ({len(status.untracked_files)}): {status.untracked_files}")
                print(f"Latest Commit:  {status.latest_commit_sha} - {status.latest_commit_message}")
                return 0
            except Exception as e:
                print(f"Git inspect error: {e}", file=sys.stderr)
                return 1
        elif parsed.git_action == "dry-run":
            try:
                plan = ctrl.dry_run(parsed.files, parsed.message)
                print(f"Plan Safe:      {plan.is_safe}")
                print(f"Target Branch:  {plan.target_branch}")
                print(f"Files:          {plan.files_to_stage}")
                print(f"Message:        {plan.commit_message}")
                if plan.warnings:
                    print(f"Warnings:       {plan.warnings}")
                return 0 if plan.is_safe else 1
            except Exception as e:
                print(f"Git dry-run error: {e}", file=sys.stderr)
                return 1

    elif parsed.subcommand == "analyze":
        from kanoman.analysis.models import AnalysisReport
        from kanoman.analysis.python_analyzer import PythonASTAnalyzer
        from kanoman.analysis.markdown_validator import MarkdownValidator

        root = Path(parsed.root).resolve() if parsed.root else config.workspace_root
        target = Path(parsed.path)
        if not target.is_absolute():
            target = (root / target).resolve()

        if parsed.analyze_action == "python":
            analyzer = PythonASTAnalyzer(workspace_root=root)
            if target.is_file():
                findings = analyzer.analyze_file(target)
                report = AnalysisReport(
                    analyzer_name="PythonASTAnalyzer",
                    workspace_root=str(root),
                    files_scanned=1,
                    findings=findings,
                )
            else:
                report = analyzer.analyze_directory(target)
        elif parsed.analyze_action == "markdown":
            validator = MarkdownValidator(workspace_root=root)
            if target.is_file():
                findings = validator.validate_file(target)
                report = AnalysisReport(
                    analyzer_name="MarkdownValidator",
                    workspace_root=str(root),
                    files_scanned=1,
                    findings=findings,
                )
            else:
                report = validator.validate_directory(target)
        else:
            print("Please specify an analysis target: python or markdown", file=sys.stderr)
            return 1

        if parsed.format == "json":
            print(report.model_dump_json(indent=2))
        else:
            print(f"=== {report.analyzer_name} Report ===")
            print(f"Files scanned: {report.files_scanned}")
            print(f"Findings:      {len(report.findings)}")
            for sev, count in report.summary_by_severity.items():
                if count > 0:
                    print(f"  - {sev}: {count}")
            if report.findings:
                print("\nFindings detail:")
                for f in report.findings:
                    pos = f":{f.line}" if f.line is not None else ""
                    print(f" [{f.severity.value}] {f.file_path}{pos} — [{f.rule_id}] {f.message}")
                    if f.recommendation:
                        print(f"     Fix: {f.recommendation}")
            else:
                print("All files passed analysis cleanly.")

        return 1 if report.has_high_or_critical else 0

    elif parsed.subcommand == "agent":
        if parsed.agent_action == "coordinate":
            # Input validation and bounding
            title = parsed.title.strip() if parsed.title else ""
            desc = parsed.desc.strip() if parsed.desc else ""
            if len(title) < 3 or len(title) > 200:
                print("Error: Task title must be between 3 and 200 characters.", file=sys.stderr)
                return 2
            if len(desc) < 5 or len(desc) > 4000:
                print("Error: Task description must be between 5 and 4000 characters.", file=sys.stderr)
                return 2
            if parsed.max_iterations < 1 or parsed.max_iterations > 20:
                print("Error: max-iterations must be between 1 and 20.", file=sys.stderr)
                return 2
            if parsed.token_budget < 100 or parsed.token_budget > 500000:
                print("Error: token-budget must be between 100 and 500000.", file=sys.stderr)
                return 2

            prov_name = (parsed.provider or config.default_ai_provider).lower()
            proj_id = getattr(parsed, "project_id", None)
            task = Task(
                title=title,
                description=desc,
                project_id=proj_id,
                priority=TaskPriority[parsed.priority],
                metadata={
                    "use_specialists": not parsed.no_specialists,
                    "provider": prov_name,
                    "max_iterations": parsed.max_iterations,
                    "token_budget": parsed.token_budget,
                },
            )

            finished = active_orch.execute_task(task, task_type="coordinate_agents")
            is_success = (finished.status.value == "COMPLETED")

            if parsed.format == "json":
                output_payload = {
                    "task_id": finished.task_id,
                    "status": finished.status.value,
                    "result_summary": finished.result_summary,
                    "checkpoint_id": finished.checkpoint_id,
                    "is_successful": is_success,
                    "sanitized_error": finished.sanitized_error,
                }
                print(json.dumps(output_payload, indent=2))
            else:
                print("=== Kanoman Multi-Agent Coordination Result ===")
                print(f"Task ID:        {finished.task_id}")
                print(f"Status:         {finished.status.value}")
                print(f"Result Summary: {finished.result_summary or 'No summary'}")
                print(f"Checkpoint:     {finished.checkpoint_id or 'None'}")
                if finished.sanitized_error:
                    print(f"Error:          {finished.sanitized_error}")

            return 0 if is_success else 1
        else:
            print("Please specify an agent action, e.g.: kanoman agent coordinate", file=sys.stderr)
            return 1

    elif parsed.subcommand == "test":
        import pytest
        return pytest.main(["-v"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
