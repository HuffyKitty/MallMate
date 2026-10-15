"""通义千问 OpenAI 兼容接口适配器。

聊天与检索服务统一通过本适配器访问模型，避免在业务节点里散落 Base URL、API Key
和模型名。只有显式调用具体方法时才会发起网络请求。
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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """把一批文本交给配置的 Embedding 模型，按输入顺序返回向量。"""

        if not texts:
            return []
        response = self.client().embeddings.create(
            model=self.models.embedding,
            input=texts,
        )
        # API 可能按 index 排序返回；显式排序可以保证向量和输入片段一一对应。
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def embed_query(self, query: str) -> list[float]:
        """查询向量使用与入库相同的 Embedding 模型和向量空间。"""

        vectors = self.embed_documents([query])
        if not vectors:
            raise RuntimeError("查询文本没有生成 Embedding 向量")
        return vectors[0]
