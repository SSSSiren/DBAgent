# ============================================================================
# LangGraph 状态图定义 — Agent 执行流程的骨架
# ============================================================================
# 这个文件定义了 LangGraph 的状态图结构，是整个 Agent 的"骨架"。
#
# LangGraph 的核心思想是状态图驱动：
#   - 节点（Node）：每个节点是一个函数，读取状态、执行逻辑、返回更新
#   - 边（Edge）：定义节点之间的连接关系
#   - 条件路由（Conditional Edge）：根据状态动态决定下一个节点
#
# 状态图结构：
#   understand → plan → act → (条件路由)
#                             ├─ 需要确认 → confirm → END
#                             ├─ 还有计划 → reflect → plan (循环)
#                             └─ 完成 → summarize → END
#
# 关键概念：
#   - StateGraph：LangGraph 的状态图类
#   - set_entry_point：设置入口节点
#   - add_edge：添加固定边（A → B）
#   - add_conditional_edges：添加条件边，根据函数返回值决定下一个节点
#   - compile()：编译状态图为可执行的 agent_graph
# ============================================================================

from typing import Literal

from langgraph.graph import END, StateGraph

from app.agent.nodes import act_node, confirm_node, plan_node, reflect_node, summarize_node, understand_node
from app.agent.state import AgentState


# ============================================================================
# 条件路由函数 — 决定状态图的走向
# ============================================================================

def should_continue_after_act(state: AgentState) -> Literal["continue", "confirm", "finish"]:
    """
    act_node 执行后的条件路由。

    判断逻辑：
    1. 如果 needs_confirmation=True → 返回 "confirm"，进入确认流程
    2. 如果 execution_plan 非空（还有工具要执行）→ 返回 "continue"，进入 reflect → plan 循环
    3. 否则 → 返回 "finish"，进入 summarize 生成最终响应

    返回值：
    - "continue"：继续执行下一个工具（经过 reflect 反思后回到 plan）
    - "confirm"：需要用户确认写操作
    - "finish"：所有工具执行完成，进入总结
    """
    if state.get("needs_confirmation"):
        return "confirm"
    if state.get("execution_plan"):
        return "continue"
    return "finish"


def should_continue_after_reflect(state: AgentState) -> Literal["continue", "finish"]:
    """
    reflect_node 执行后的条件路由。

    判断逻辑：
    1. 如果 current_step="continue" 且 execution_plan 非空 → 返回 "continue"，回到 plan
    2. 否则 → 返回 "finish"，进入 summarize

    返回值：
    - "continue"：还有工具要执行，回到 plan 节点
    - "finish"：所有工具执行完成，进入 summarize 节点
    """
    if state.get("current_step") == "continue" and state.get("execution_plan"):
        return "continue"
    return "finish"


# ============================================================================
# 构建状态图
# ============================================================================

# 创建状态图，传入 AgentState 作为状态类型
workflow = StateGraph(AgentState)

# -----------------------------------------------------------------------
# 添加节点 — 每个节点是一个异步函数
# -----------------------------------------------------------------------
workflow.add_node("understand", understand_node)    # 理解用户意图
workflow.add_node("plan", plan_node)                # 规划执行步骤
workflow.add_node("act", act_node)                  # 执行工具调用
workflow.add_node("reflect", reflect_node)          # 反思执行结果
workflow.add_node("summarize", summarize_node)      # 生成最终响应
workflow.add_node("confirm", confirm_node)          # 等待用户确认

# -----------------------------------------------------------------------
# 添加边 — 定义节点之间的连接关系
# -----------------------------------------------------------------------

# 设置入口节点：所有请求从 understand 开始
workflow.set_entry_point("understand")

# 固定边：understand → plan → act（这三个节点总是按顺序执行）
workflow.add_edge("understand", "plan")
workflow.add_edge("plan", "act")

# 条件边：act 之后根据状态决定走向
workflow.add_conditional_edges(
    "act",
    should_continue_after_act,              # 路由函数
    {
        "continue": "reflect",              # 还有工具要执行 → reflect
        "confirm": "confirm",               # 需要确认 → confirm
        "finish": "summarize",              # 完成 → summarize
    },
)

# 条件边：reflect 之后根据状态决定走向
workflow.add_conditional_edges(
    "reflect",
    should_continue_after_reflect,          # 路由函数
    {
        "continue": "plan",                 # 还有工具要执行 → 回到 plan（循环）
        "finish": "summarize",              # 完成 → summarize
    },
)

# 固定边：confirm 和 summarize 都是终止节点，执行完后结束
workflow.add_edge("confirm", END)
workflow.add_edge("summarize", END)

# -----------------------------------------------------------------------
# 编译状态图 — 生成可执行的 agent_graph
# ----------------------------------------------------------------===========
# compile() 将状态图编译为一个可执行的 LangGraph 对象
# 这个对象支持 astream()、invoke() 等方法，用于启动 Agent 执行
agent_graph = workflow.compile()
