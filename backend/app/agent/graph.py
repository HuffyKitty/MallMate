"""组装并编译 MallMate 工作流。

图结构与请求无关，因此模块加载时编译一次；每次请求只通过 context 注入本次数据库服务。
"""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    answer_faq,
    answer_handoff,
    answer_order,
    classify,
    route_after_classify,
)
from app.agent.state import AgentContext, AgentState


def create_agent_graph():
    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("classify", classify)
    builder.add_node("faq", answer_faq)
    builder.add_node("order", answer_order)
    builder.add_node("handoff", answer_handoff)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {"faq": "faq", "order": "order", "handoff": "handoff"},
    )
    builder.add_edge("faq", END)
    builder.add_edge("order", END)
    builder.add_edge("handoff", END)
    return builder.compile(name="mallmate_customer_service")


agent_graph = create_agent_graph()

