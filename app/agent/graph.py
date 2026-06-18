from typing import Literal

from langgraph.graph import END, StateGraph

from app.agent.nodes import act_node, confirm_node, plan_node, reflect_node, summarize_node, understand_node
from app.agent.state import AgentState


def should_continue_after_act(state: AgentState) -> Literal["continue", "confirm", "finish"]:
    if state.get("needs_confirmation"):
        return "confirm"
    if state.get("execution_plan"):
        return "continue"
    return "finish"


def should_continue_after_reflect(state: AgentState) -> Literal["continue", "finish"]:
    if state.get("current_step") == "continue" and state.get("execution_plan"):
        return "continue"
    return "finish"


workflow = StateGraph(AgentState)
workflow.add_node("understand", understand_node)
workflow.add_node("plan", plan_node)
workflow.add_node("act", act_node)
workflow.add_node("reflect", reflect_node)
workflow.add_node("summarize", summarize_node)
workflow.add_node("confirm", confirm_node)

workflow.set_entry_point("understand")
workflow.add_edge("understand", "plan")
workflow.add_edge("plan", "act")
workflow.add_conditional_edges(
    "act",
    should_continue_after_act,
    {
        "continue": "reflect",
        "confirm": "confirm",
        "finish": "summarize",
    },
)
workflow.add_conditional_edges("reflect", should_continue_after_reflect, {"continue": "plan", "finish": "summarize"})
workflow.add_edge("confirm", END)
workflow.add_edge("summarize", END)

agent_graph = workflow.compile()
