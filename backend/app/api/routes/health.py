"""进程存活检查。"""

from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    # 这里只验证 Web 进程能响应；数据库等依赖的就绪检查后续单独增加。
    return {"status": "ok", "mode": settings.environment}

