"""LangGraph 节点。

每个节点只负责一个步骤：分类、FAQ、订单处理或人工转接。节点通过 AgentState 交换
结果，通过 Runtime Context 调用业务服务。
"""

import re

from langgraph.runtime import Runtime

from app.agent.state import AgentContext, AgentState
from app.agent.intent import classify_intent
from app.core.enums import Intent
from app.core.exceptions import ResourceNotFoundError


def classify(state: AgentState) -> AgentState:
    """调用可解释的 10 类意图基线；后续在同一接口中融合 Qwen 结果。"""

    prediction = classify_intent(state["message"])
    return {
        "intent": prediction.intent,
        "urgency": prediction.urgency,
        "confidence": prediction.confidence,
        "matched_keywords": list(prediction.matched_keywords),
    }


def answer_faq(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    """检索可信知识；没有证据时明确降级，不生成猜测答案。"""

    evidence = runtime.context.knowledge.search(state["message"])
    if evidence is None:
        return {
            "answer": "目前没有找到足够可靠的资料。请补充商品或问题细节，或联系人工客服。",
            "sources": [],
        }
    return {
        "answer": evidence.content,
        "sources": [
            {
                "title": evidence.title,
                "version": evidence.version,
                "uri": evidence.uri,
            }
        ],
    }


def answer_order(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    """处理订单、物流和退换货入口，业务事实全部来自 OrderService。"""

    match = re.search(r"\d{4,}", state["message"])
    if match is None:
        return {"answer": "请提供订单号，我会查询当前演示账号下的订单。", "sources": []}

    order_id = int(match.group())
    try:
        order = runtime.context.orders.get_owned_order(state["customer_id"], order_id)
    except ResourceNotFoundError:
        return {"answer": "当前账号下没有找到该订单，请核对订单号。", "sources": []}

    if state["intent"] in {
        Intent.REFUND_REQUEST,
        Intent.RETURN_REQUEST,
        Intent.EXCHANGE_REQUEST,
        Intent.DAMAGED_PRODUCT,
        Intent.MISSING_PRODUCT,
        Intent.WRONG_PRODUCT,
    }:
        evidence_hint = "；破损、少件或错发问题还需要上传清晰凭证" if state["intent"] in {
            Intent.DAMAGED_PRODUCT,
            Intent.MISSING_PRODUCT,
            Intent.WRONG_PRODUCT,
        } else ""
        return {
            "answer": (
                f"订单 {order.id} 状态为 {order.status}。"
                f"请在下方售后表单填写申请原因，查看资格预览后确认提交{evidence_hint}。"
            ),
            "sources": [],
        }
    if state["intent"] in {Intent.LOGISTICS_QUERY, Intent.LOGISTICS_ABNORMAL}:
        logistics = runtime.context.orders.get_logistics_data(state["customer_id"], order_id)
        return {
            "answer": (
                f"订单 {order_id} 的物流状态为 {logistics['status']}；"
                f"最后更新时间：{logistics['updated_at'] or '暂无'}。"
            ),
            "sources": [],
        }

    order_data = runtime.context.orders.get_order_data(state["customer_id"], order_id)
    items = "、".join(
        f"{item['name']} ×{item['quantity']}" for item in order_data["items"]
    )
    return {"answer": f"订单 {order.id} 状态为 {order.status}，商品：{items}。", "sources": []}


def answer_handoff(_: AgentState) -> AgentState:
    """人工分支占位；后续在这里调用受控的建单工具。"""

    return {
        "answer": "已识别为需要人工处理的问题。当前框架尚未接入客服工单队列，请使用人工渠道继续处理。",
        "sources": [],
    }


def route_after_classify(state: AgentState) -> str:
    """根据结构化意图选择下一节点。"""

    if state["intent"] == Intent.HUMAN_HANDOFF:
        return "handoff"
    # 含订单号的问题优先查业务事实；纯政策问法交给知识库回答。
    if re.search(r"\d{4,}", state["message"]):
        return "order"
    if state["intent"] in {Intent.ORDER_QUERY, Intent.LOGISTICS_QUERY, Intent.LOGISTICS_ABNORMAL}:
        return "order"
    if any(word in state["message"] for word in ("怎么", "如何", "条件", "规则", "政策", "多久", "运费")):
        return "faq"
    return "order"

