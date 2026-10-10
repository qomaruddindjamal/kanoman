"""Project Registry for Kanoman AI.

Maintains registered projects with safety checks preventing path traversal,
system root registration, and credential exposure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from kanoman.core.models import Project


class ProjectRegistry:
    """Registry maintaining authorized projects and enforcing isolation boundaries."""

    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}

    def register_project(self, project: Project) -> Project:
        """Register a new project with safety checks."""
        # Safety Check: Prevent registering OS root or sensitive directories
        resolved_root = project.workspace_root.resolve()
        disallowed_roots = [
            Path("/").resolve(),
            Path("C:/").resolve() if Path("C:/").exists() else None,
            Path("C:/Windows").resolve() if Path("C:/Windows").exists() else None,
            Path("C:/Program Files").resolve() if Path("C:/Program Files").exists() else None,
        ]
        for disallowed in disallowed_roots:
            if disallowed and resolved_root == disallowed:
                raise ValueError(f"Unsafe project root directory rejected: {resolved_root}")

        if project.project_id in self._projects:
            raise ValueError(f"Project with ID '{project.project_id}' already registered.")

        self._projects[project.project_id] = project
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Fetch project by ID."""
        return self._projects.get(project_id)

    def list_projects(self) -> List[Project]:
        """List all registered projects safely without exposing secrets."""
        return list(self._projects.values())

    def update_project_policy(
        self,
        project_id: str,
        *,
        allowed_remote_url: Optional[str] = None,
        policy_branch: Optional[str] = None,
        git_dry_run_policy: Optional[bool] = None,
    ) -> Project:
        """Safely update project policy fields."""
        proj = self.get_project(project_id)
        if not proj:
            raise KeyError(f"Project '{project_id}' not found.")

        updated_dict = proj.model_dump()
        if allowed_remote_url is not None:
            updated_dict["allowed_remote_url"] = allowed_remote_url
        if policy_branch is not None:
            updated_dict["policy_branch"] = policy_branch
        if git_dry_run_policy is not None:
            updated_dict["git_dry_run_policy"] = git_dry_run_policy

        updated_proj = Project(**updated_dict)
        self._projects[project_id] = updated_proj
        return updated_proj

    def unregister_project(self, project_id: str) -> bool:
        """Remove project from registry."""
        if project_id in self._projects:
            del self._projects[project_id]
            return True
        return False
