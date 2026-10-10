import json
import pytest
import anyio
from kanoman.mcp.server import create_mcp_server


@pytest.mark.anyio
async def test_mcp_server_lists_tools():
    server = create_mcp_server("test-mcp")
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    assert "kanoman_status" in tool_names
    assert "kanoman_list_projects" in tool_names
    assert "kanoman_run_task" in tool_names
    assert "kanoman_git_inspect" in tool_names


@pytest.mark.anyio
async def test_mcp_server_executes_status_tool():
    server = create_mcp_server("test-mcp")
    res = await server.call_tool("kanoman_status", {})
    # In MCP 2.x, call_tool returns a CallToolResult whose content is a list of TextContent/ImageContent
    assert res is not None
    text_content = res.content[0].text
    status_data = json.loads(text_content)
    assert status_data["environment"] == "development"
    assert "workspace_root" in status_data
