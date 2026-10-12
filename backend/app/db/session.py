"""数据库 Engine、Session 工厂和 FastAPI 会话依赖。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _engine_options() -> dict:
    """按数据库类型生成连接选项。

    SQLite 的线程参数只服务于本机演示；PostgreSQL 才启用可配置的连接池参数。
    """

    common = {"pool_pre_ping": True, "echo": settings.database_echo}
    if settings.database_url.startswith("sqlite"):
        return {**common, "connect_args": {"check_same_thread": False}}
    return {
        **common,
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout_seconds,
    }


engine = create_engine(settings.database_url, **_engine_options())
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """每个请求创建一个会话，请求结束后自动关闭。"""

    with SessionLocal() as session:
        yield session

