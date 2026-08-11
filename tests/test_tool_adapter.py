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


@pytest.mark.asyncio
async def test_optional_args_use_python_defaults_not_none():
    """回归：StructuredTool 缺省可选字段时，应使用工具签名的 Python 默认值，
    而非 pydantic 的 None。

    背景：find_table(max_results=200) 的 max_results 非 required。
    旧实现 `_make_args_schema` 把非 required 字段 default=None，
    导致 LLM 只传 keyword 时 max_results=None 传入，
    `min(None, 500)` 抛 TypeError: '<' not supported between instances of
    'int' and 'NoneType'（真实环境 SSE 中反复出现）。
    """
    tools = build_deepagent_tools()
    by_name = {t.name: t for t in tools}
    tool = by_name["find_table"]
    # 只传 required 字段 keyword，max_results 缺省
    # 修复前：max_results=None → min(None,500) 抛 TypeError
    # 修复后：max_results 取 handler 默认 200
    result = await tool.ainvoke({"keyword": "nonexistent_table_xyz"})
    assert isinstance(result, str)
    assert "未找到" in result  # 走到正常搜索路径，而非 TypeError


@pytest.mark.asyncio
async def test_optional_args_defaults_match_handler_for_all_affected_tools():
    """回归：所有带非 None 默认值的可选字段，缺省时都取工具签名默认值而非 None。

    受影响工具：find_table(max_results=200)、list_databases(keyword='', env_type='test')、
    query_database(summary='')。
    """
    from pydantic.v1 import BaseModel
    tools = build_deepagent_tools()
    for t in tools:
        schema = t.args_schema
        assert issubclass(schema, BaseModel)
        # pydantic v1 的 create_model 类字段元数据在 __fields__
        defaults = schema.__fields__
        if t.name == "find_table":
            assert defaults["max_results"].default == 200
        elif t.name == "list_databases":
            assert defaults["keyword"].default == ""
            assert defaults["env_type"].default == "test"
        elif t.name == "query_database":
            assert defaults["summary"].default == ""