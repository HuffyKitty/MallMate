"""ChromaDB 稠密向量检索适配器；本模块只返回片段 ID，不信任向量库里的原文。"""

import chromadb

from app.core.config import Settings


class ChromaVectorSearch:
    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query_embedding: list[float], *, limit: int = 20) -> list[str]:
        """向现有集合做近邻查询，并只返回有效文档对应的子片段 ID。"""

        client = chromadb.HttpClient(
            host=self.settings.chroma_host,
            port=self.settings.chroma_port,
        )
        collection = client.get_collection(self.settings.chroma_collection)
        count = collection.count()
        if count == 0:
            return []

        # 查询数不能超过集合大小；状态过滤避免召回已停用的政策版本。
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, count),
            where={"status": "active"},
            include=["metadatas"],
        )
        return result.get("ids", [[]])[0]
