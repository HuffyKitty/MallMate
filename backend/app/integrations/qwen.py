"""通义千问 OpenAI 兼容接口适配器。

本轮只完成配置、客户端装配和职责映射，不会主动发起网络请求。Agent 后续只能依赖
本适配器，避免在节点里散落 Base URL、API Key 和模型名。
"""

from dataclasses import dataclass
from enum import StrEnum

from openai import OpenAI

from app.core.config import Settings


class QwenTask(StrEnum):
    CHAT = "chat"
    INTENT = "intent"
    VISION = "vision"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass(frozen=True)
class QwenModelCatalog:
    chat: str
    intent: str
    vision: str
    embedding: str
    rerank: str

    def for_task(self, task: QwenTask) -> str:
        return getattr(self, task.value)


class QwenGateway:
    """集中管理千问模型选择；构造对象不会调用外部服务。"""

    def __init__(self, settings: Settings):
        self.enabled = settings.llm_enabled
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.models = QwenModelCatalog(
            chat=settings.llm_chat_model,
            intent=settings.llm_intent_model,
            vision=settings.llm_vision_model,
            embedding=settings.llm_embedding_model,
            rerank=settings.llm_rerank_model,
        )

    def client(self) -> OpenAI:
        """仅在真正调用模型时创建客户端，并在缺配置时尽早失败。"""

        if not self.enabled:
            raise RuntimeError("LLM 当前关闭；请先设置 MALLMATE_LLM_ENABLED=true")
        if self.api_key is None or not self.api_key.get_secret_value():
            raise RuntimeError("缺少 MALLMATE_LLM_API_KEY")
        if not self.base_url or "YOUR_WORKSPACE_ID" in self.base_url:
            raise RuntimeError("请配置与 API Key 同地域的 MALLMATE_LLM_BASE_URL")
        return OpenAI(
            api_key=self.api_key.get_secret_value(),
            base_url=self.base_url,
            timeout=30.0,
            max_retries=2,
        )
