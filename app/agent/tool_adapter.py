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
            args_schema=_make_args_schema(
                tool_def.name, tool_def.parameters, tool_def.handler
            ),
        )
        tools.append(tool)
    return tools


def _make_async_handler(name: str):
    """包装 registry.execute 为可被 langchain 调用的 async 函数。"""
    async def _handler(**kwargs) -> str:
        return await registry.execute(name, **kwargs)
    _handler.__name__ = name
    return _handler


def _make_args_schema(name: str, parameters: dict, handler=None):
    """将 OpenAI parameters 字典转换为 pydantic schema 类。

    注意：langchain_core 1.5.x 不再提供 langchain_core.pydantic_v1，
    改用与 pydantic 2.x 一起打包的 pydantic.v1，其 create_model/Field 与
    StructuredTool.from_function 完全兼容。

    仅把 parameters["required"] 中的字段设为必填；非 required 字段的默认值
    从 handler 的 Python 签名读取（而非固定 None），否则 LLM 缺省该字段时
    pydantic 会把 None 传入 handler，绕过 Python 默认值——例如
    find_table(max_results=200) 会收到 max_results=None，触发
    min(None, 500) 抛 TypeError。实测真实环境 SSE 中即复现此错误。
    """
    import inspect

    from pydantic.v1 import create_model, Field
    props = parameters.get("properties", {})
    required = set(parameters.get("required", []))

    # 从 handler 签名读取 Python 默认值（缺省字段的语义来源）
    python_defaults: dict[str, object] = {}
    if handler is not None:
        for pname, p in inspect.signature(handler).parameters.items():
            if p.default is not inspect.Parameter.empty:
                python_defaults[pname] = p.default

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
            # 优先用工具签名默认值；无默认值时才是 None（保持可选语义）
            default = python_defaults.get(pname)
            fields[pname] = (
                Optional[pytype],
                Field(
                    default=default,
                    description=pdef.get("description", ""),
                ),
            )
    return create_model(f"{name}Args", **fields)