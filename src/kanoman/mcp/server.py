"""Model Context Protocol (MCP) Server for Kanoman AI.

Exposes limited, validated domain tools to AI agents:
- kanoman_status
- kanoman_list_projects
- kanoman_run_task
- kanoman_git_inspect

Mitigates privilege escalation by strictly preventing arbitrary shell execution.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from mcp.server.mcpserver import MCPServer
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import get_config
from kanoman.core.models import Task, TaskPriority
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry
from kanoman.git.controller import GitController


def create_mcp_server(name: str = "kanoman-mcp") -> MCPServer:
    """Create and configure the Kanoman MCP server."""
    server = MCPServer(name)
    config = get_config()
    registry = ProjectRegistry()
    orchestrator = TaskOrchestrator(config=config, registry=registry)

    @server.tool()
    def kanoman_status() -> str:
        """Get the current operational status of the Kanoman AI engine."""
        recovery = RecoveryEngine(config.checkpoint_dir)
        latest_chk = recovery.get_latest_checkpoint()
        status_data = {
            "environment": config.env.value,
            "workspace_root": str(config.workspace_root),
            "git_dry_run": config.git_dry_run,
            "allowed_remote": config.git_allowed_remote,
            "default_ai_provider": config.default_ai_provider,
            "latest_checkpoint": latest_chk.checkpoint_id if latest_chk else None,
        }
        return json.dumps(status_data, indent=2)

    @server.tool()
    def kanoman_list_projects() -> str:
        """List all authorized projects currently registered with Kanoman."""
        projs = registry.list_projects()
        data = [
            {
                "project_id": p.project_id,
                "name": p.name,
                "workspace_root": str(p.workspace_root),
                "policy_branch": p.policy_branch,
            }
            for p in projs
        ]
        return json.dumps(data, indent=2)

    @server.tool()
    def kanoman_run_task(title: str, description: str, task_type: str = "ping") -> str:
        """Execute a validated development task within Kanoman Orchestrator."""
        task = Task(title=title, description=description, priority=TaskPriority.MEDIUM)
        finished = orchestrator.execute_task(task, task_type=task_type)
        return json.dumps(
            {
                "task_id": finished.task_id,
                "status": finished.status.value,
                "result_summary": finished.result_summary,
                "checkpoint_id": finished.checkpoint_id,
            },
            indent=2,
        )

    @server.tool()
    def kanoman_git_inspect() -> str:
        """Inspect the current Git repository status safely without mutations."""
        ctrl = GitController(
            workspace_root=config.workspace_root,
            allowed_remote=config.git_allowed_remote,
            allowed_branches=config.git_allowed_branches,
            config=config,
        )
        status = ctrl.inspect()
        return json.dumps(
            {
                "current_branch": status.current_branch,
                "is_clean": status.is_clean,
                "staged_count": len(status.staged_files),
                "unstaged_count": len(status.unstaged_files),
                "untracked_count": len(status.untracked_files),
                "latest_commit_sha": status.latest_commit_sha,
                "latest_commit_message": status.latest_commit_message,
            },
            indent=2,
        )

    return server
