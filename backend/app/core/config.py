"""应用配置。

配置统一从 ``backend/.env`` 或 ``MALLMATE_`` 前缀的环境变量读取。
这里使用绝对路径定位 .env，避免从不同工作目录启动时读取到不同配置。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    # 演示身份会接受客户端提供的 X-Demo-User，因此必须由本机配置显式开启。
    # 配置文件缺失或环境变量拼错时保持关闭，避免服务以可冒充身份的模式启动。
    demo_mode: bool = False
    # 自动写入公开开发账号同样采用失败关闭。setup.ps1 生成的本机 .env 会按需
    # 显式开启，生产配置则由下面的校验器强制禁止。
    seed_demo_data: bool = False

    database_url: str = "sqlite:///./mallmate_dev_v2.db"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 30

    cors_origins: str = "http://localhost:3000"

    # 正式认证默认由环境配置显式开启，避免缺少密钥时误以为系统已经受到保护。
    # scripts/setup.ps1 会为本机生成不进入 Git 的随机密钥并开启认证。
    auth_enabled: bool = False
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "mallmate-api"
    jwt_audience: str = "mallmate-web"
    # 非正有效期会让服务成功启动、却只签发立即失效的令牌。把错误提前到配置
    # 解析阶段，避免登录接口在运行期持续返回看似成功但无法使用的凭据。
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=7, gt=0)
    refresh_cookie_name: str = "mallmate_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

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
        """启动时拒绝明显不安全的生产配置，而不是带着风险继续运行。"""

        if self.environment == Environment.PRODUCTION and (self.demo_mode or self.seed_demo_data):
            raise ValueError("生产环境必须关闭 demo_mode 和 seed_demo_data")
        if self.environment == Environment.PRODUCTION and not self.auth_enabled:
            raise ValueError("生产环境必须开启 auth_enabled")

        secret = self.jwt_secret.get_secret_value()
        if self.auth_enabled and len(secret) < 32:
            raise ValueError("开启认证时 MALLMATE_JWT_SECRET 至少需要 32 个字符")
        if self.jwt_algorithm != "HS256":
            raise ValueError("当前版本只允许经过验证的 HS256 JWT 算法")
        # SameSite=None 的 Cookie 必须同时带 Secure；否则现代浏览器会直接拒收，
        # 后端却仍返回登录成功，最终表现为刷新和会话恢复一直失败。
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("Cookie SameSite=None 时必须开启 Cookie Secure")

        if self.environment == Environment.PRODUCTION:
            if not self.cookie_secure:
                raise ValueError("生产环境必须开启 Cookie Secure")
            if "*" in self.allowed_origins:
                raise ValueError("生产环境 CORS 不允许使用通配来源")
            if "mallmate_dev_only" in self.database_url:
                raise ValueError("生产环境不能使用默认数据库密码")
            if self.minio_secret_key.get_secret_value() == "mallmate_dev_only":
                raise ValueError("生产环境不能使用默认 MinIO 密码")
        return self


@lru_cache
def get_settings() -> Settings:
    """全进程只解析一次配置，供依赖注入和应用装配复用。"""

    return Settings()


settings = get_settings()

