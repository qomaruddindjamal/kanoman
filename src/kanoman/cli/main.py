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
    run_t.add_argument("--title", required=True, help="Task title.")
    run_t.add_argument("--desc", required=True, help="Task description.")
    run_t.add_argument("--type", default="ping", help="Task type (default: ping).")
    run_t.add_argument("--priority", default="MEDIUM", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])

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

    # Subcommand: test
    subparsers.add_parser("test", help="Execute test suite via pytest.")

    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    config = get_config()

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
        registry = ProjectRegistry()
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
            orchestrator = TaskOrchestrator(config=config)
            task = Task(
                title=parsed.title,
                description=parsed.desc,
                priority=TaskPriority[parsed.priority],
            )
            finished = orchestrator.execute_task(task, task_type=parsed.type)
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

    elif parsed.subcommand == "test":
        import pytest
        return pytest.main(["-v"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
