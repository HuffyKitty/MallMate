"""应用配置。

配置统一从 ``backend/.env`` 或 ``MALLMATE_`` 前缀的环境变量读取。
这里使用绝对路径定位 .env，避免从不同工作目录启动时读取到不同配置。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import Environment


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="MALLMATE_",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    demo_mode: bool = True
    seed_demo_data: bool = True

    database_url: str = "sqlite:///./mallmate_dev_v2.db"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 30

    cors_origins: str = "http://localhost:3000"

    # 基础设施连接信息。开发环境可不启动这些服务，Docker 环境由 compose 注入。
    redis_url: str = "redis://localhost:6379/0"
    chroma_host: str = "localhost"
    chroma_port: int = 18000
    chroma_collection: str = "mallmate_knowledge"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "mallmate"
    minio_secret_key: SecretStr = SecretStr("mallmate_dev_only")
    minio_bucket: str = "mallmate-evidence"

    # 通义千问模型按职责分别配置，后续可以独立替换或做 A/B 评估。
    # API Key 只写入本机 backend/.env，不进入代码和 Git。
    llm_enabled: bool = False
    llm_provider: str = "dashscope"
    llm_base_url: str | None = None
    llm_chat_model: str = "qwen-plus"
    llm_intent_model: str = "qwen-flash"
    llm_vision_model: str = "qwen-vl-plus"
    llm_embedding_model: str = "text-embedding-v4"
    llm_rerank_model: str = "qwen3-rerank"
    llm_api_key: SecretStr | None = None

    prometheus_enabled: bool = True

    @property
    def allowed_origins(self) -> list[str]:
        """把逗号分隔的环境变量转换成 CORS 所需的来源列表。"""

        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def reject_demo_options_in_production(self) -> "Settings":
        """防止生产环境误启用演示身份或自动写入演示数据。"""

        if self.environment == Environment.PRODUCTION and (self.demo_mode or self.seed_demo_data):
            raise ValueError("生产环境必须关闭 demo_mode 和 seed_demo_data")
        return self


@lru_cache
def get_settings() -> Settings:
    """全进程只解析一次配置，供依赖注入和应用装配复用。"""

    return Settings()


settings = get_settings()

