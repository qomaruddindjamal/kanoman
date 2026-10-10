"""Model Context Protocol (MCP) Server for Kanoman AI.

Exposes limited, validated domain tools to AI agents:
- kanoman_status
- kanoman_list_projects
- kanoman_run_task
- kanoman_git_inspect
- kanoman_coordinate_agents
- kanoman_get_agent_decision

Mitigates privilege escalation by strictly preventing arbitrary shell execution,
enforcing AgentQualityGate on proposals, and forbidding autonomous git commit/push.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.config.settings import KanomanConfig, get_config
from kanoman.core.models import Task, TaskPriority
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry
from kanoman.git.controller import GitController
from kanoman.logging.logger import redact_sensitive_text


def create_mcp_server(
    name: str = "kanoman-mcp",
    config: Optional[KanomanConfig] = None,
    orchestrator: Optional[TaskOrchestrator] = None,
    recovery_engine: Optional[RecoveryEngine] = None,
    project_registry: Optional[ProjectRegistry] = None,
) -> MCPServer:
    """Create and configure the Kanoman MCP server."""
    server = MCPServer(name)
    active_config = config or get_config()
    recovery = recovery_engine or RecoveryEngine(active_config.checkpoint_dir)
    registry = project_registry or ProjectRegistry(storage_file=active_config.workspace_root / ".kanoman_projects.json")
    active_orchestrator = orchestrator or TaskOrchestrator(
        config=active_config, registry=registry, recovery_engine=recovery
    )

    @server.tool()
    def kanoman_status() -> str:
        """Get the current operational status of the Kanoman AI engine."""
        latest_chk = recovery.get_latest_checkpoint()
        status_data = {
            "environment": active_config.env.value,
            "workspace_root": str(active_config.workspace_root),
            "git_dry_run": active_config.git_dry_run,
            "allowed_remote": active_config.git_allowed_remote,
            "default_ai_provider": active_config.default_ai_provider,
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
        finished = active_orchestrator.execute_task(task, task_type=task_type)
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
            workspace_root=active_config.workspace_root,
            allowed_remote=active_config.git_allowed_remote,
            allowed_branches=active_config.git_allowed_branches,
            config=active_config,
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

    @server.tool()
    def kanoman_coordinate_agents(
        title: str,
        description: str,
        max_iterations: int = 5,
        use_specialists: bool = True,
        provider: str = "mock",
    ) -> str:
        """Run multi-agent coordination workflow with specialist personas and quality gate."""
        if not isinstance(title, str) or not isinstance(description, str):
            return json.dumps(
                {"is_successful": False, "error": "Invalid argument types: title and description must be strings."},
                indent=2,
            )
        clean_title = title.strip()
        clean_desc = description.strip()
        if len(clean_title) < 3 or len(clean_title) > 200:
            return json.dumps(
                {"is_successful": False, "error": "Validation failed: title must be between 3 and 200 characters."},
                indent=2,
            )
        if len(clean_desc) < 5 or len(clean_desc) > 4000:
            return json.dumps(
                {
                    "is_successful": False,
                    "error": "Validation failed: description must be between 5 and 4000 characters.",
                },
                indent=2,
            )
        if not isinstance(max_iterations, int) or max_iterations < 1 or max_iterations > 20:
            return json.dumps(
                {"is_successful": False, "error": "Validation failed: max_iterations must be an integer between 1 and 20."},
                indent=2,
            )
        clean_provider = (provider or "mock").lower().strip()
        if clean_provider not in ("mock", "gemini"):
            return json.dumps(
                {"is_successful": False, "error": f"Validation failed: unsupported provider '{clean_provider}'."},
                indent=2,
            )

        try:
            task = Task(
                title=clean_title,
                description=clean_desc,
                priority=TaskPriority.MEDIUM,
                metadata={
                    "use_specialists": bool(use_specialists),
                    "provider": clean_provider,
                    "max_iterations": max_iterations,
                },
            )
            finished = active_orchestrator.execute_task(task, task_type="coordinate_agents")
            is_success = (finished.status.value == "COMPLETED")
            return json.dumps(
                {
                    "task_id": finished.task_id,
                    "status": finished.status.value,
                    "result_summary": finished.result_summary,
                    "checkpoint_id": finished.checkpoint_id,
                    "is_successful": is_success,
                    "error": finished.sanitized_error,
                },
                indent=2,
            )
        except Exception as exc:
            sanitized = redact_sensitive_text(str(exc))
            return json.dumps(
                {
                    "task_id": None,
                    "status": "FAILED",
                    "result_summary": None,
                    "checkpoint_id": None,
                    "is_successful": False,
                    "error": sanitized,
                },
                indent=2,
            )

    @server.tool()
    def kanoman_get_agent_decision(checkpoint_id: str) -> str:
        """Retrieve recorded agent decisions and audit trail from a recovery checkpoint."""
        if not isinstance(checkpoint_id, str):
            return json.dumps(
                {"is_successful": False, "error": "Invalid argument: checkpoint_id must be a string."},
                indent=2,
            )
        clean_id = checkpoint_id.strip()
        if not re.match(r"^chk_[a-zA-Z0-9_\-]{1,64}$", clean_id):
            return json.dumps(
                {"is_successful": False, "error": "Validation failed: invalid checkpoint_id format."},
                indent=2,
            )

        try:
            chk = recovery.load_checkpoint(clean_id)
            return json.dumps(
                {
                    "is_successful": True,
                    "checkpoint_id": chk.checkpoint_id,
                    "task_id": chk.task_id,
                    "status": chk.status,
                    "change_summary": chk.change_summary,
                    "test_results": chk.test_results,
                    "next_steps": chk.next_steps,
                },
                indent=2,
            )
        except Exception as exc:
            sanitized = redact_sensitive_text(str(exc))
            return json.dumps(
                {"is_successful": False, "error": f"Failed to load checkpoint: {sanitized}"},
                indent=2,
            )

    return server
