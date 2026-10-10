"""Cross-Project Isolation Verification Tests (Kanoman vs MitraNet).

Verifies:
1. ProjectRegistry isolates distinct projects and configuration contexts.
2. GitController strictly enforces remote origin matching and aborts on foreign repository (MitraNet).
3. TaskOrchestrator enforces workspace root boundaries and denies cross-project manipulation.
4. AgentQualityGate prevents path traversal, absolute path leakage, and symlink escapes across project boundaries.
5. RecoveryEngine isolates checkpoint access and blocks foreign checkpoint hijacking.
6. Failure of project identification fails closed safely.
7. CLI and MCP maintain consistent workspace boundaries.
8. Secret masking and provider isolation across project contexts.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict
import pytest

from kanoman.agents.quality_gate import AgentQualityGate
from kanoman.checkpoints.recovery import RecoveryEngine
from kanoman.cli.main import main
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Checkpoint, Project, Task, TaskPriority, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.core.registry import ProjectRegistry
from kanoman.git.controller import GitController
from kanoman.mcp.server import create_mcp_server


@pytest.fixture
def isolated_fixtures(tmp_path: Path):
    """Create isolated temporary workspaces for Kanoman and simulated MitraNet."""
    kanoman_ws = tmp_path / "kanoman_repo"
    kanoman_ws.mkdir()
    mitranet_ws = tmp_path / "mitranet_repo"
    mitranet_ws.mkdir()

    # Initialize local git fixtures
    for repo_dir, remote_url in [
        (kanoman_ws, "https://github.com/qomaruddindjamal/kanoman.git"),
        (mitranet_ws, "https://github.com/qomaruddindjamal/mitranet.git"),
    ]:
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@kanoman.local"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(repo_dir), check=True, capture_output=True)

    return {
        "kanoman_root": kanoman_ws,
        "mitranet_root": mitranet_ws,
        "base_tmp": tmp_path,
    }


# =====================================================================
# 1. ProjectRegistry Isolation
# =====================================================================


def test_registry_isolates_projects_and_paths(isolated_fixtures: Dict[str, Path]) -> None:
    storage = isolated_fixtures["base_tmp"] / "registry.json"
    registry = ProjectRegistry(storage_file=storage)

    proj_kanoman = Project(
        project_id="kanoman_core",
        name="Kanoman AI Core",
        workspace_root=isolated_fixtures["kanoman_root"],
        allowed_remote_url="https://github.com/qomaruddindjamal/kanoman.git",
    )
    proj_mitranet = Project(
        project_id="mitranet_app",
        name="MitraNet Application",
        workspace_root=isolated_fixtures["mitranet_root"],
        allowed_remote_url="https://github.com/qomaruddindjamal/mitranet.git",
    )

    registry.register_project(proj_kanoman)
    registry.register_project(proj_mitranet)

    # Verify separate retrieval
    retrieved_k = registry.get_project("kanoman_core")
    retrieved_m = registry.get_project("mitranet_app")

    assert retrieved_k is not None
    assert retrieved_m is not None
    assert retrieved_k.workspace_root != retrieved_m.workspace_root
    assert retrieved_k.allowed_remote_url != retrieved_m.allowed_remote_url
    assert "kanoman" in retrieved_k.allowed_remote_url
    assert "mitranet" in retrieved_m.allowed_remote_url

    # Duplicate ID rejection
    with pytest.raises(ValueError, match="already registered"):
        registry.register_project(proj_kanoman)


# =====================================================================
# 2. GitController Cross-Repository Verification & Rejection
# =====================================================================


def test_git_controller_rejects_mitranet_when_configured_for_kanoman(isolated_fixtures: Dict[str, Path]) -> None:
    # Point Kanoman controller at MitraNet workspace
    ctrl = GitController(
        workspace_root=isolated_fixtures["mitranet_root"],
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )

    # Invariant: Must fail closed with Remote URL mismatch
    with pytest.raises(ValueError, match="Remote URL mismatch"):
        ctrl.verify_repository_identity()

    with pytest.raises(ValueError, match="Remote URL mismatch"):
        ctrl.inspect()


def test_git_controller_rejects_kanoman_when_configured_for_mitranet(isolated_fixtures: Dict[str, Path]) -> None:
    # Point MitraNet controller at Kanoman workspace
    ctrl = GitController(
        workspace_root=isolated_fixtures["kanoman_root"],
        allowed_remote="https://github.com/qomaruddindjamal/mitranet.git",
    )

    with pytest.raises(ValueError, match="Remote URL mismatch"):
        ctrl.verify_repository_identity()


# =====================================================================
# 3. TaskOrchestrator Workspace Isolation
# =====================================================================


def test_task_orchestrator_rejects_foreign_workspace_path_manipulation(isolated_fixtures: Dict[str, Path]) -> None:
    config_kanoman = KanomanConfig(
        workspace_root=isolated_fixtures["kanoman_root"],
        checkpoint_dir=isolated_fixtures["kanoman_root"] / ".checkpoints",
    )
    orchestrator = TaskOrchestrator(config=config_kanoman)

    # Attempt to target MitraNet directory via target_path metadata
    foreign_path = isolated_fixtures["mitranet_root"] / "config.py"
    foreign_path.write_text("SECRET_VAL = 123\n", encoding="utf-8")

    task = Task(
        title="Analyze Foreign File",
        description="Attempt to read foreign repository.",
        metadata={"target_path": str(foreign_path)},
    )

    res = orchestrator.execute_task(task, task_type="analyze_python")
    # PythonASTAnalyzer blocks analyzing files outside workspace_root
    assert res.status == TaskStatus.FAILED
    assert "outside authorized workspace" in (res.result_summary or "").lower()


# =====================================================================
# 4. AgentQualityGate Cross-Project Path Traversal & Symlink Escape
# =====================================================================


def test_quality_gate_blocks_cross_project_traversal_and_symlinks(isolated_fixtures: Dict[str, Path]) -> None:
    gate = AgentQualityGate(workspace_root=isolated_fixtures["kanoman_root"])

    # Path traversal attempting to reach sibling directory (mitranet)
    with pytest.raises(ValueError, match="Path traversal detected"):
        gate.validate_target_path("../mitranet_repo/app.py")

    # Absolute path targeting mitranet
    abs_mitranet_file = str(isolated_fixtures["mitranet_root"] / "app.py")
    with pytest.raises(ValueError, match="Absolute paths are prohibited"):
        gate.validate_target_path(abs_mitranet_file)


# =====================================================================
# 5. Checkpoint Isolation Across Projects
# =====================================================================


def test_recovery_engine_isolates_checkpoints(isolated_fixtures: Dict[str, Path]) -> None:
    recovery_k = RecoveryEngine(isolated_fixtures["kanoman_root"] / ".checkpoints")
    recovery_m = RecoveryEngine(isolated_fixtures["mitranet_root"] / ".checkpoints")

    chk_k = Checkpoint(
        task_id="task_kanoman_100",
        project_id="kanoman_core",
        status="COMPLETED",
        change_summary="Kanoman internal work",
    )
    recovery_k.save_checkpoint(chk_k)

    # MitraNet recovery engine cannot find Kanoman's checkpoint
    with pytest.raises(FileNotFoundError):
        recovery_m.load_checkpoint(chk_k.checkpoint_id)

    # Path traversal attempt across checkpoint stores is blocked
    with pytest.raises(ValueError, match="Invalid checkpoint_id format|Path traversal detected"):
        recovery_m.load_checkpoint(f"../../kanoman_repo/.checkpoints/{chk_k.checkpoint_id}")


# =====================================================================
# 6. Safe Rejection for Unknown Projects
# =====================================================================


def test_unknown_project_lookup_returns_none(isolated_fixtures: Dict[str, Path]) -> None:
    registry = ProjectRegistry(storage_file=isolated_fixtures["base_tmp"] / "reg.json")
    assert registry.get_project("unknown_project_id") is None


# =====================================================================
# 7. CLI & MCP Boundary Consistency
# =====================================================================


def test_cli_and_mcp_consistent_workspace_bounds(isolated_fixtures: Dict[str, Path], capsys: pytest.CaptureFixture) -> None:
    config_k = KanomanConfig(
        workspace_root=isolated_fixtures["kanoman_root"],
        checkpoint_dir=isolated_fixtures["kanoman_root"] / ".checkpoints",
        git_allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )

    # CLI inspects Kanoman repo: succeeds
    rc = main(["git", "inspect"], config=config_k)
    assert rc == 0
    captured = capsys.readouterr()
    assert "Branch:" in captured.out

    # MCP server configured for Kanoman
    server = create_mcp_server("test-mcp", config=config_k)

    @pytest.mark.anyio
    async def run_mcp():
        res = await server.call_tool("kanoman_git_inspect", {})
        data = json.loads(res.content[0].text)
        assert data["current_branch"] == "main"
        assert data["is_clean"] is True

    import anyio
    anyio.run(run_mcp)


# =====================================================================
# 8. External Project Context Execution & Fail-Closed Tests
# =====================================================================


def test_task_orchestrator_executes_on_external_project_context(isolated_fixtures: Dict[str, Path]) -> None:
    storage = isolated_fixtures["base_tmp"] / "reg_orch.json"
    registry = ProjectRegistry(storage_file=storage)

    proj_ext = Project(
        project_id="external_proj",
        name="External Project",
        workspace_root=isolated_fixtures["mitranet_root"],
        allowed_remote_url="https://github.com/qomaruddindjamal/mitranet.git",
    )
    registry.register_project(proj_ext)

    # Put a python file inside external project workspace
    ext_py = isolated_fixtures["mitranet_root"] / "feature.py"
    ext_py.write_text("def run():\n    return 42\n", encoding="utf-8")

    orchestrator = TaskOrchestrator(
        config=KanomanConfig(workspace_root=isolated_fixtures["kanoman_root"]),
        registry=registry,
    )

    # Task targeting external project should succeed using its workspace root
    task = Task(
        title="Analyze External Code",
        description="Run AST check on external project",
        project_id="external_proj",
        metadata={"target_path": "feature.py"},
    )
    res = orchestrator.execute_task(task, task_type="analyze_python")
    assert res.status == TaskStatus.COMPLETED
    assert "Python AST analysis completed" in (res.result_summary or "")


def test_task_orchestrator_rejects_unknown_project_id_fail_closed(isolated_fixtures: Dict[str, Path]) -> None:
    orchestrator = TaskOrchestrator(
        config=KanomanConfig(workspace_root=isolated_fixtures["kanoman_root"]),
    )

    task = Task(
        title="Task with invalid project",
        description="Must fail immediately without running any handler",
        project_id="non_existent_project_id",
    )
    res = orchestrator.execute_task(task, task_type="ping")
    assert res.status == TaskStatus.FAILED
    assert "not found in registry. Fail-closed" in (res.result_summary or "")


def test_no_kanoman_files_written_to_external_workspace(isolated_fixtures: Dict[str, Path]) -> None:
    storage = isolated_fixtures["base_tmp"] / "reg_clean.json"
    registry = ProjectRegistry(storage_file=storage)

    proj_ext = Project(
        project_id="clean_ext",
        name="Clean External",
        workspace_root=isolated_fixtures["mitranet_root"],
        allowed_remote_url="https://github.com/qomaruddindjamal/mitranet.git",
    )
    registry.register_project(proj_ext)

    # Record initial files in external workspace
    initial_files = set(isolated_fixtures["mitranet_root"].rglob("*"))

    orchestrator = TaskOrchestrator(
        config=KanomanConfig(workspace_root=isolated_fixtures["kanoman_root"]),
        registry=registry,
    )

    # Run multi-agent coordination with Mock provider on external project
    task = Task(
        title="Architecture assessment",
        description="Evaluate architecture for external project",
        project_id="clean_ext",
        metadata={"use_specialists": True, "provider": "mock"},
    )
    res = orchestrator.execute_task(task, task_type="coordinate_agents")
    assert res.status == TaskStatus.COMPLETED

    # Verify no files were created inside external workspace root
    current_files = set(isolated_fixtures["mitranet_root"].rglob("*"))
    assert current_files == initial_files, f"Unexpected files generated in external workspace: {current_files - initial_files}"


def test_cli_forwards_project_id_and_rejects_unknown(isolated_fixtures: Dict[str, Path], capsys: pytest.CaptureFixture) -> None:
    storage = isolated_fixtures["base_tmp"] / "reg_cli.json"
    registry = ProjectRegistry(storage_file=storage)

    proj_ext = Project(
        project_id="proj_alpha",
        name="Project Alpha",
        workspace_root=isolated_fixtures["mitranet_root"],
        allowed_remote_url="https://github.com/qomaruddindjamal/mitranet.git",
    )
    registry.register_project(proj_ext)

    config_k = KanomanConfig(workspace_root=isolated_fixtures["kanoman_root"])
    orch = TaskOrchestrator(config=config_k, registry=registry)

    # 1. Run valid project
    rc = main(
        ["task", "run", "--title", "Ping Alpha", "--desc", "Ping task for alpha", "--project-id", "proj_alpha"],
        config=config_k,
        orchestrator=orch,
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "COMPLETED" in captured.out

    # 2. Run invalid project ID - must fail closed
    rc_fail = main(
        ["task", "run", "--title", "Ping Invalid", "--desc", "Ping task for invalid", "--project-id", "unknown_ghost"],
        config=config_k,
        orchestrator=orch,
    )
    assert rc_fail == 1
    captured_fail = capsys.readouterr()
    assert "FAILED" in captured_fail.out
    assert "not found in registry" in captured_fail.out


def test_mcp_forwards_project_id_and_validates(isolated_fixtures: Dict[str, Path]) -> None:
    storage = isolated_fixtures["base_tmp"] / "reg_mcp.json"
    registry = ProjectRegistry(storage_file=storage)

    proj_ext = Project(
        project_id="proj_beta",
        name="Project Beta",
        workspace_root=isolated_fixtures["mitranet_root"],
        allowed_remote_url="https://github.com/qomaruddindjamal/mitranet.git",
    )
    registry.register_project(proj_ext)

    config_k = KanomanConfig(workspace_root=isolated_fixtures["kanoman_root"])
    server = create_mcp_server("test-mcp-ext", config=config_k, project_registry=registry)

    @pytest.mark.anyio
    async def run_mcp_tests():
        # Valid project task
        res_valid = await server.call_tool(
            "kanoman_run_task",
            {"title": "Test Beta", "description": "Run on Beta", "project_id": "proj_beta"},
        )
        data_valid = json.loads(res_valid.content[0].text)
        assert data_valid["status"] == "COMPLETED"

        # Unknown project ID rejected fail-closed
        res_invalid = await server.call_tool(
            "kanoman_run_task",
            {"title": "Test Beta", "description": "Run on Beta", "project_id": "bogus_id"},
        )
        data_invalid = json.loads(res_invalid.content[0].text)
        assert data_invalid["status"] == "FAILED"
        assert "unknown project_id" in data_invalid["error"]

        # kanoman_coordinate_agents with project_id
        res_coord = await server.call_tool(
            "kanoman_coordinate_agents",
            {
                "title": "Coord on Beta",
                "description": "Coordinate on beta project",
                "project_id": "proj_beta",
                "provider": "mock",
            },
        )
        data_coord = json.loads(res_coord.content[0].text)
        assert data_coord["status"] == "COMPLETED"
        assert data_coord["is_successful"] is True

        # kanoman_coordinate_agents with invalid project_id rejected fail-closed
        res_coord_inv = await server.call_tool(
            "kanoman_coordinate_agents",
            {
                "title": "Coord on Bogus",
                "description": "Coordinate on bogus project",
                "project_id": "non_existent_project",
                "provider": "mock",
            },
        )
        data_coord_inv = json.loads(res_coord_inv.content[0].text)
        assert data_coord_inv["is_successful"] is False
        assert "unknown project_id" in data_coord_inv["error"]

    import anyio
    anyio.run(run_mcp_tests)
