"""
AgentExecutor 封装 - 基于 LangGraph 的 ReAct Agent
"""

from typing import Any
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage

from app.agent.llm import get_llm
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.tools import (
    list_databases_tool,
    select_database_tool,
    list_tables_tool,
    describe_table_tool,
    query_database_tool,
    execute_sql_tool,
    ask_user_tool,
)
from app.memory.summary import update_summary


def create_agent_executor():
    """
    创建 Agent 实例

    Returns:
        CompiledStateGraph: 配置好的 Agent 执行器
    """
    # 获取 LLM
    llm = get_llm()

    # 定义工具列表
    tools = [
        list_databases_tool,
        select_database_tool,
        list_tables_tool,
        describe_table_tool,
        query_database_tool,
        execute_sql_tool,
        ask_user_tool,
    ]

    # 创建 ReAct agent
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=AGENT_SYSTEM_PROMPT,
    )

    return agent


async def run_agent(
    user_input: str,
    session_state: dict[str, Any],
) -> dict[str, Any]:
    """
    运行 Agent

    Args:
        user_input: 用户输入
        session_state: 会话状态

    Returns:
        包含 response 和 updated_state 的字典
    """
    # 创建 Agent
    agent = create_agent_executor()

    # 准备输入
    chat_history = session_state.get("chat_history", [])
    summary = session_state.get("summary", "")
    selected_schema_id = session_state.get("selected_schema_id")
    selected_database = session_state.get("selected_database")

    # 构建上下文提示
    context_parts = []
    if selected_database:
        context_parts.append(f"当前选择的数据库: {selected_database.get('schemaName')} (schema_id={selected_schema_id})")
    if summary:
        context_parts.append(f"对话摘要: {summary}")

    # 如果有上下文，添加到用户输入前面
    if context_parts:
        context = "\n".join(context_parts)
        full_input = f"{context}\n\n用户问题: {user_input}"
    else:
        full_input = user_input

    # 运行 Agent
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=full_input)],
    })

    # 提取响应
    messages = result.get("messages", [])
    response = messages[-1].content if messages else ""

    # 检查是否有写操作需要确认
    needs_confirmation = False
    pending_action = None

    # 更新对话历史
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=response))

    # 保持最近 20 条消息
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    # 更新摘要
    new_summary = await update_summary(summary, user_input, response)

    # 构建更新后的状态
    updated_state = {
        "chat_history": chat_history,
        "summary": new_summary,
        "selected_schema_id": selected_schema_id,
        "selected_database": selected_database,
    }

    return {
        "response": response,
        "updated_state": updated_state,
        "needs_confirmation": needs_confirmation,
        "pending_action": pending_action,
    }
