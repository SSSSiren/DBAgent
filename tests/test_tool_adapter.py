import pytest
from langchain_core.tools import BaseTool
from app.agent.tool_adapter import build_deepagent_tools
from app.tools import registry


def test_builds_all_six_tools():
    tools = build_deepagent_tools()
    assert len(tools) == len(registry.tool_names) >= 6
    for t in tools:
        assert isinstance(t, BaseTool)
        assert t.name in registry.tool_names
        assert t.description


@pytest.mark.asyncio
async def test_tool_invokes_registry_handler():
    tools = build_deepagent_tools()
    by_name = {t.name: t for t in tools}
    # list_databases 有默认参数，直接调用应返回字符串
    tool = by_name["list_databases"]
    result = await tool.ainvoke({"keyword": ""})
    assert isinstance(result, str)