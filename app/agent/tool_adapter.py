"""将现有 ToolRegistry 的 6 个工具适配为 langchain StructuredTool。

关键点：
- 复用现有 registry.execute()，保留中间件（timeout/error_normalize）与幻觉参数过滤
- 工具 schema 从 registry 的 OpenAI parameters 转换
- async handler 包装为 langchain 可调用的工具
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool

from app.tools import registry


def build_deepagent_tools() -> list[StructuredTool]:
    """从现有 registry 构建 langchain StructuredTool 列表。"""
    tools: list[StructuredTool] = []
    for tool_def in registry:
        tool = StructuredTool.from_function(
            coroutine=_make_async_handler(tool_def.name),
            name=tool_def.name,
            description=tool_def.description,
            args_schema=_make_args_schema(tool_def.name, tool_def.parameters),
        )
        tools.append(tool)
    return tools


def _make_async_handler(name: str):
    """包装 registry.execute 为可被 langchain 调用的 async 函数。"""
    async def _handler(**kwargs) -> str:
        return await registry.execute(name, **kwargs)
    _handler.__name__ = name
    return _handler


def _make_args_schema(name: str, parameters: dict):
    """将 OpenAI parameters 字典转换为 pydantic schema 类。

    注意：langchain_core 1.5.x 不再提供 langchain_core.pydantic_v1，
    改用与 pydantic 2.x 一起打包的 pydantic.v1，其 create_model/Field 与
    StructuredTool.from_function 完全兼容。

    仅把 parameters["required"] 中的字段设为必填，其余字段设默认值 None，
    否则 brief 中以部分参数（如 {"keyword": ""}）调用工具会因缺字段校验失败。
    """
    from pydantic.v1 import create_model, Field
    props = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    fields = {}
    for pname, pdef in props.items():
        ptype = pdef.get("type", "string")
        if ptype == "integer":
            pytype = int
        elif ptype == "number":
            pytype = float
        elif ptype == "boolean":
            pytype = bool
        else:
            pytype = str
        if pname in required:
            fields[pname] = (pytype, Field(description=pdef.get("description", "")))
        else:
            fields[pname] = (
                Optional[pytype],
                Field(default=None, description=pdef.get("description", "")),
            )
    return create_model(f"{name}Args", **fields)