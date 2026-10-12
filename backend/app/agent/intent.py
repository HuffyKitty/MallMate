"""不依赖大模型的意图基线。

这个模块有两个目的：
1. 没有 API Key 时，整个工作流仍可开发和评估；
2. 接入通义千问后，作为低置信度回退和回归测试基线。

它不是最终的语义分类器。真实上线时会把规则分数、Embedding 相似度和
Qwen 结构化输出做融合，但枚举与返回结构保持不变。
"""

from dataclasses import dataclass

from app.core.enums import Intent, Urgency


@dataclass(frozen=True)
class IntentPrediction:
    intent: Intent
    urgency: Urgency
    confidence: float
    matched_keywords: tuple[str, ...]


# 顺序也是平分时的优先级：风险和明确售后问题优先于普通查询。
INTENT_KEYWORDS: dict[Intent, tuple[str, ...]] = {
    Intent.HUMAN_HANDOFF: ("人工", "客服", "投诉", "12315", "负责人", "经理"),
    Intent.DAMAGED_PRODUCT: ("破损", "坏了", "裂开", "碎了", "碎的", "漏液", "无法开机", "质量问题"),
    Intent.MISSING_PRODUCT: ("少件", "少了", "漏发", "缺件", "空包", "数量不对"),
    Intent.WRONG_PRODUCT: ("发错", "错发", "货不对版", "型号不对", "颜色不对"),
    Intent.LOGISTICS_ABNORMAL: ("不更新", "没更新", "一直没到", "没收到", "丢件", "丢了", "停滞", "卡住", "卡在", "异常"),
    Intent.EXCHANGE_REQUEST: ("换货", "换一个", "换成", "换码", "换尺寸", "换颜色"),
    Intent.RETURN_REQUEST: ("退货", "退回", "七天无理由", "不想要", "不要了"),
    Intent.REFUND_REQUEST: ("退款", "退钱", "钱没退", "退款到账", "取消订单"),
    Intent.LOGISTICS_QUERY: ("物流", "快递", "到哪", "配送", "运单", "什么时候到"),
    Intent.ORDER_QUERY: ("订单", "下单", "购买记录", "订单状态", "是否发货"),
}


def classify_intent(message: str) -> IntentPrediction:
    """用可解释规则得到意图、紧急度和置信度。

    命中多个意图时，先比较关键词命中数，再使用上面的风险优先级。
    规则未命中时回退到订单查询，并给出低置信度，未来由 Agent 追问。
    """

    normalized = message.strip().lower()
    scored: list[tuple[int, int, Intent, tuple[str, ...]]] = []
    for priority, (intent, keywords) in enumerate(INTENT_KEYWORDS.items()):
        matched = tuple(keyword for keyword in keywords if keyword in normalized)
        if matched:
            scored.append((len(matched), -priority, intent, matched))

    if not scored:
        return IntentPrediction(Intent.ORDER_QUERY, Urgency.NORMAL, 0.35, ())

    hit_count, _, intent, matched = max(scored)
    confidence = min(0.95, 0.62 + 0.11 * hit_count)
    urgency = _infer_urgency(normalized, intent)
    return IntentPrediction(intent, urgency, confidence, matched)


def _infer_urgency(message: str, intent: Intent) -> Urgency:
    if any(word in message for word in ("人身安全", "起火", "爆炸", "触电", "受伤", "食品安全")):
        return Urgency.URGENT
    if any(word in message for word in ("高额", "多次失败", "欺诈", "泄露", "12315")):
        return Urgency.HIGH
    if intent in {
        Intent.LOGISTICS_ABNORMAL,
        Intent.DAMAGED_PRODUCT,
        Intent.MISSING_PRODUCT,
        Intent.WRONG_PRODUCT,
        Intent.HUMAN_HANDOFF,
    }:
        return Urgency.MEDIUM
    return Urgency.NORMAL
