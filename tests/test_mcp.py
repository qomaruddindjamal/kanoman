"""Comprehensive unit and integration tests for Kanoman MCP Server and agent tools.

Tests:
1. Tool registry exposes all authorized tools (status, list_projects, run_task, git_inspect, coordinate_agents, get_agent_decision).
2. Schema inspection for multi-agent tools.
3. Execution of status tool.
4. Execution of coordinate_agents tool with MockAIProvider (success path).
5. Input boundary and malformed argument rejection (title, desc, max_iterations, provider).
6. Quality Gate and Security Auditor veto enforcement through MCP.
7. Zero secret leak in MCP error payloads.
8. Checkpoint decision inspection via get_agent_decision tool.
9. Path traversal rejection in get_agent_decision tool.
10. Absence of autonomous Git commit/push tools in MCP toolset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import pytest
import anyio

from kanoman.ai.models import AIErrorType, AIException, AIMessage, AIResponse, UsageMetadata
from kanoman.ai.mock import MockAIProvider
from kanoman.config.settings import KanomanConfig
from kanoman.core.models import Checkpoint, Task, TaskPriority, TaskStatus
from kanoman.core.orchestrator import TaskOrchestrator
from kanoman.mcp.server import create_mcp_server


class InsecureMockProvider(MockAIProvider):
    """Mock provider generating eval() call to test MCP quality gate veto."""

    def generate_structured(
        self,
        messages: List[AIMessage],
        schema: Dict[str, Any],
        temperature: float = 0.2,
    ) -> AIResponse:
        insecure_data = {
            "target_path": "src/kanoman/dyn.py",
            "proposed_content": "import os\n\ndef run(s: str):\n    eval(s)\n",
            "rationale": "Dynamic execution proposal.",
        }
        return AIResponse(
            provider="mock",
            model_name="mock-insecure",
            content=json.dumps(insecure_data),
            structured_data=insecure_data,
            usage=UsageMetadata(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def test_config(temp_workspace: Path) -> KanomanConfig:
    return KanomanConfig(
        workspace_root=temp_workspace,
        checkpoint_dir=temp_workspace / ".kanoman_checkpoints",
        default_ai_provider="mock",
    )


# =====================================================================
# 1. MCP Tool Registration & Schema Inspection
# =====================================================================


@pytest.mark.anyio
async def test_mcp_server_lists_tools(test_config: KanomanConfig) -> None:
    server = create_mcp_server("test-mcp", config=test_config)
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    # Required baseline tools
    assert "kanoman_status" in tool_names
    assert "kanoman_list_projects" in tool_names
    assert "kanoman_run_task" in tool_names
    assert "kanoman_git_inspect" in tool_names

    # Multi-agent tools
    assert "kanoman_coordinate_agents" in tool_names
    assert "kanoman_get_agent_decision" in tool_names

    # SECURITY INVARIANT: No autonomous commit or push tools
    assert "kanoman_git_commit" not in tool_names
    assert "kanoman_git_push" not in tool_names
    assert "kanoman_shell_exec" not in tool_names


@pytest.mark.anyio
async def test_mcp_server_executes_status_tool(test_config: KanomanConfig) -> None:
    server = create_mcp_server("test-mcp", config=test_config)
    res = await server.call_tool("kanoman_status", {})
    assert res is not None
    text_content = res.content[0].text
    status_data = json.loads(text_content)
    assert status_data["environment"] == "development"
    assert "workspace_root" in status_data
    assert status_data["default_ai_provider"] == "mock"


# =====================================================================
# 2. MCP kanoman_coordinate_agents: Success Path
# =====================================================================


@pytest.mark.anyio
async def test_mcp_coordinate_agents_success(test_config: KanomanConfig) -> None:
    server = create_mcp_server("test-mcp", config=test_config)
    res = await server.call_tool(
        "kanoman_coordinate_agents",
        {
            "title": "Build Hash Utility",
            "description": "Construct SHA256 helper module.",
            "max_iterations": 3,
            "use_specialists": True,
            "provider": "mock",
        },
    )
    assert res is not None
    data = json.loads(res.content[0].text)
    assert data["is_successful"] is True
    assert data["status"] == "COMPLETED"
    assert data["task_id"] is not None
    assert data["checkpoint_id"] is not None
    assert data["error"] is None


# =====================================================================
# 3. MCP Input Validation & Malformed Payload Rejection
# =====================================================================


@pytest.mark.anyio
async def test_mcp_coordinate_agents_input_validation(test_config: KanomanConfig) -> None:
    server = create_mcp_server("test-mcp", config=test_config)

    # Title too short (< 3 chars)
    res_short_title = await server.call_tool(
        "kanoman_coordinate_agents",
        {"title": "ab", "description": "Valid description."},
    )
    data1 = json.loads(res_short_title.content[0].text)
    assert data1["is_successful"] is False
    assert "Validation failed: title must be between 3 and 200 characters" in data1["error"]

    # Description too short (< 5 chars)
    res_short_desc = await server.call_tool(
        "kanoman_coordinate_agents",
        {"title": "Valid Title", "description": "tiny"},
    )
    data2 = json.loads(res_short_desc.content[0].text)
    assert data2["is_successful"] is False
    assert "Validation failed: description must be between 5 and 4000 characters" in data2["error"]

    # max_iterations out of bounds
    res_iter = await server.call_tool(
        "kanoman_coordinate_agents",
        {"title": "Valid Title", "description": "Valid description.", "max_iterations": 99},
    )
    data3 = json.loads(res_iter.content[0].text)
    assert data3["is_successful"] is False
    assert "max_iterations must be an integer between 1 and 20" in data3["error"]

    # Unsupported provider
    res_prov = await server.call_tool(
        "kanoman_coordinate_agents",
        {"title": "Valid Title", "description": "Valid description.", "provider": "unsupported_llm"},
    )
    data4 = json.loads(res_prov.content[0].text)
    assert data4["is_successful"] is False
    assert "unsupported provider" in data4["error"]


# =====================================================================
# 4. MCP Security Veto Enforcement
# =====================================================================


@pytest.mark.anyio
async def test_mcp_coordinate_agents_security_veto(test_config: KanomanConfig) -> None:
    insecure_orch = TaskOrchestrator(config=test_config)

    def insecure_coord_handler(task: Task, cfg: Any, reg: Any) -> Dict[str, Any]:
        from kanoman.agents.coordinator import MultiAgentCoordinator
        from kanoman.agents.quality_gate import AgentQualityGate
        from kanoman.agents.runners import (
            ArchitectRunner,
            CoderRunner,
            SecurityAuditorRunner,
            QAEngineerRunner,
            execute_end_to_end_specialist_workflow,
        )
        gate = AgentQualityGate(cfg.workspace_root)
        coord = MultiAgentCoordinator(config=cfg, quality_gate=gate)
        p = InsecureMockProvider()
        res = execute_end_to_end_specialist_workflow(
            task=task,
            coordinator=coord,
            architect=ArchitectRunner(p),
            coder=CoderRunner(p),
            auditor=SecurityAuditorRunner(p),
            qa=QAEngineerRunner(p),
            quality_gate=gate,
        )
        if not res.is_successful:
            raise ValueError(f"Multi-agent coordination rejected (security veto): {res.error or 'Blocked by quality gate'}")
        return {"coordinator_result": res.model_dump()}

    insecure_orch.register_handler("coordinate_agents", insecure_coord_handler)

    server = create_mcp_server("test-mcp", config=test_config, orchestrator=insecure_orch)
    res = await server.call_tool(
        "kanoman_coordinate_agents",
        {
            "title": "Insecure Eval Task",
            "description": "Attempt dynamic code execution.",
        },
    )
    data = json.loads(res.content[0].text)
    assert data["is_successful"] is False
    assert data["status"] == "FAILED"
    assert "security veto" in data["error"].lower()


# =====================================================================
# 5. MCP Zero Secret Leak
# =====================================================================


@pytest.mark.anyio
async def test_mcp_error_sanitization_masks_secrets(test_config: KanomanConfig) -> None:
    failing_orch = TaskOrchestrator(config=test_config)
    dummy_secret = "AIzaSy" + "A" * 33

    def failing_handler(task: Task, cfg: Any, reg: Any) -> Dict[str, Any]:
        raise AIException(
            error_type=AIErrorType.SERVICE_UNAVAILABLE,
            message=f"Leaked key: {dummy_secret}",
            provider="mock",
        )

    failing_orch.register_handler("coordinate_agents", failing_handler)
    server = create_mcp_server("test-mcp", config=test_config, orchestrator=failing_orch)

    res = await server.call_tool(
        "kanoman_coordinate_agents",
        {
            "title": "Failing Task",
            "description": "Test exception handling.",
        },
    )
    raw_response = res.content[0].text
    data = json.loads(raw_response)
    assert data["is_successful"] is False
    assert dummy_secret not in raw_response
    assert "***REDACTED_SECRET***" in data["error"]


# =====================================================================
# 6. MCP Decision Inspection & Path Traversal Prevention
# =====================================================================


@pytest.mark.anyio
async def test_mcp_get_agent_decision_success(test_config: KanomanConfig) -> None:
    server = create_mcp_server("test-mcp", config=test_config)

    # 1. Run a task to create a valid checkpoint
    run_res = await server.call_tool(
        "kanoman_coordinate_agents",
        {"title": "Valid Plan", "description": "Create helper."},
    )
    run_data = json.loads(run_res.content[0].text)
    chk_id = run_data["checkpoint_id"]
    assert chk_id is not None

    # 2. Inspect checkpoint decisions
    inspect_res = await server.call_tool("kanoman_get_agent_decision", {"checkpoint_id": chk_id})
    inspect_data = json.loads(inspect_res.content[0].text)
    assert inspect_data["is_successful"] is True
    assert inspect_data["checkpoint_id"] == chk_id
    assert inspect_data["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_mcp_get_agent_decision_path_traversal_rejection(test_config: KanomanConfig) -> None:
    server = create_mcp_server("test-mcp", config=test_config)

    malicious_ids = [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "chk_123/../../secret",
        "chk_123;rm -rf /",
    ]

    for bad_id in malicious_ids:
        res = await server.call_tool("kanoman_get_agent_decision", {"checkpoint_id": bad_id})
        data = json.loads(res.content[0].text)
        assert data["is_successful"] is False
        assert "invalid checkpoint_id format" in data["error"]
