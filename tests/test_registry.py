import pytest
from pathlib import Path
from kanoman.core.models import Project
from kanoman.core.registry import ProjectRegistry


def test_project_registration_and_retrieval(tmp_path: Path):
    registry = ProjectRegistry()
    project = Project(
        project_id="test_proj",
        name="Test Project",
        workspace_root=tmp_path,
        allowed_remote_url="https://github.com/qomaruddindjamal/kanoman.git",
    )
    registry.register_project(project)

    retrieved = registry.get_project("test_proj")
    assert retrieved is not None
    assert retrieved.name == "Test Project"
    assert len(registry.list_projects()) == 1


def test_registry_rejects_duplicate_registration(tmp_path: Path):
    registry = ProjectRegistry()
    project = Project(
        project_id="test_proj",
        name="Test Project",
        workspace_root=tmp_path,
        allowed_remote_url="https://github.com/qomaruddindjamal/kanoman.git",
    )
    registry.register_project(project)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_project(project)


def test_registry_rejects_root_directory():
    registry = ProjectRegistry()
    root_proj = Project(
        project_id="root_proj",
        name="Root Project",
        workspace_root=Path("C:/"),
        allowed_remote_url="https://github.com/qomaruddindjamal/kanoman.git",
    )
    with pytest.raises(ValueError, match="Unsafe project root directory rejected"):
        registry.register_project(root_proj)
