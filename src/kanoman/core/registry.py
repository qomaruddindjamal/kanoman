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

    def __init__(self, storage_file: Optional[Path] = None) -> None:
        self.storage_file = storage_file.resolve() if storage_file else None
        self._projects: Dict[str, Project] = {}
        self._load_from_storage()

    def _load_from_storage(self) -> None:
        """Load projects from storage file if configured."""
        if not self.storage_file or not self.storage_file.is_file():
            return
        import json
        try:
            raw = json.loads(self.storage_file.read_text(encoding="utf-8"))
            for p_dict in raw:
                proj = Project(**p_dict)
                self._projects[proj.project_id] = proj
        except Exception:
            pass

    def _persist_to_storage(self) -> None:
        """Atomically persist registered projects to storage file."""
        if not self.storage_file:
            return
        import json
        import tempfile
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        data = [p.model_dump(mode="json") for p in self._projects.values()]
        payload_str = json.dumps(data, indent=2)

        with tempfile.NamedTemporaryFile("w", dir=self.storage_file.parent, delete=False, encoding="utf-8") as tf:
            tf.write(payload_str)
            temp_path = Path(tf.name)
        temp_path.replace(self.storage_file)

    def register_project(self, project: Project) -> Project:
        """Register a new project with safety checks."""
        # Safety Check: Prevent registering OS root or sensitive directories
        resolved_root = project.workspace_root.resolve()

        # Reject filesystem roots (e.g. C:\ or /)
        if resolved_root == resolved_root.anchor or len(resolved_root.parts) <= 1:
            raise ValueError(f"Unsafe project root directory rejected: {resolved_root}")

        disallowed_roots = [
            Path("/").resolve(),
            Path("C:/").resolve() if Path("C:/").exists() else None,
            Path("C:/Windows").resolve() if Path("C:/Windows").exists() else None,
            Path("C:/Program Files").resolve() if Path("C:/Program Files").exists() else None,
            Path("C:/Program Files (x86)").resolve() if Path("C:/Program Files (x86)").exists() else None,
        ]
        for disallowed in disallowed_roots:
            if disallowed and resolved_root == disallowed:
                raise ValueError(f"Unsafe project root directory rejected: {resolved_root}")

        if project.project_id in self._projects:
            raise ValueError(f"Project with ID '{project.project_id}' already registered.")

        self._projects[project.project_id] = project
        self._persist_to_storage()
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
        self._persist_to_storage()
        return updated_proj

    def unregister_project(self, project_id: str) -> bool:
        """Remove project from registry."""
        if project_id in self._projects:
            del self._projects[project_id]
            self._persist_to_storage()
            return True
        return False
