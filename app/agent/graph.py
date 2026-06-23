"""
Agent 执行图 - 基于 LangGraph 的 Agent 驱动流程
"""

from typing import Any, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

from app.agent.state import AgentState
from app.agent.llm_agent import run_agent


async def agent_node(state: AgentState) -> dict[str, Any]:
    """
    Agent 节点 - 运行 LLM Agent

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    user_input = state.get("user_input", "")

    # 运行 Agent
    result = await run_agent(
        user_input=user_input,
        session_state=state,
    )

    # 更新状态
    updated_state = {
        "response": result["response"],
        "chat_history": result["updated_state"]["chat_history"],
        "summary": result["updated_state"]["summary"],
        "selected_schema_id": result["updated_state"]["selected_schema_id"],
        "selected_database": result["updated_state"]["selected_database"],
        "needs_confirmation": result["needs_confirmation"],
        "pending_action": result["pending_action"],
    }

    return updated_state


async def confirm_node(state: AgentState) -> dict[str, Any]:
    """
    确认节点 - 处理写操作确认

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    pending_action = state.get("pending_action", {})

    # 生成确认提示
    sql = pending_action.get("args", {}).get("sql", "")
    response = (
        f"检测到写操作，需要确认：\n\n"
        f"```sql\n{sql}\n```\n\n"
        f"是否执行此操作？请回复 '确认执行' 或 '取消'。"
    )

    return {
        "response": response,
    }


def should_continue(state: AgentState) -> Literal["confirm", "end"]:
    """
    判断是否继续执行

    Args:
        state: 当前状态

    Returns:
        下一个节点名称
    """
    if state.get("needs_confirmation"):
        return "confirm"
    return "end"


# 创建状态图
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("agent", agent_node)
workflow.add_node("confirm", confirm_node)

# 设置入口
workflow.set_entry_point("agent")

# 添加条件边
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "confirm": "confirm",
        "end": END,
    },
)

# confirm 节点直接结束
workflow.add_edge("confirm", END)

# 编译图
agent_graph = workflow.compile()
