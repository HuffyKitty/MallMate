"""MallMate FastAPI 应用入口。

本文件只负责应用装配：生命周期、中间件、异常处理和路由。具体业务放在 services，
数据库查询放在 repositories，Agent 流程放在 agent，避免入口文件持续膨胀。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.bootstrap.seed import seed_demo
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.observability.metrics import PrometheusMiddleware, metrics_response


@asynccontextmanager
async def lifespan(_: FastAPI):
    """开发模式的启动准备。

    create_all 只作为当前过渡方案；引入 Alembic 后，生产启动不再自动改表结构。
    """

    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo(db)
    yield


def create_app() -> FastAPI:
    """应用工厂，便于未来为测试或不同部署环境创建独立应用实例。"""

    application = FastAPI(
        title="MallMate API",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Demo-User", "Idempotency-Key"],
    )
    if settings.prometheus_enabled:
        application.add_middleware(PrometheusMiddleware)
        application.add_route("/metrics", metrics_response, methods=["GET"], include_in_schema=False)
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()

