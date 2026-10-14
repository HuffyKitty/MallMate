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
from app.db.session import SessionLocal
from app.observability.metrics import PrometheusMiddleware, metrics_response


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用启动后按配置补充幂等演示数据；表结构统一由 Alembic 管理。"""

    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo(db)
    yield


def create_app() -> FastAPI:
    """应用工厂，便于未来为测试或不同部署环境创建独立应用实例。"""

    application = FastAPI(
        title="MallMate API",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,  # 必须是明确来源，不能与凭据模式混用通配符
        allow_credentials=True,  # 刷新令牌保存在 HttpOnly Cookie，需要浏览器携带凭据
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    if settings.prometheus_enabled:
        application.add_middleware(PrometheusMiddleware)
        application.add_route("/metrics", metrics_response, methods=["GET"], include_in_schema=False)
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()

