"""集中挂载所有 API 子路由。"""

from fastapi import APIRouter

from app.api.routes import after_sales, chat, health, orders


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(chat.router, prefix="/api/v1")
api_router.include_router(orders.router, prefix="/api/v1")
api_router.include_router(after_sales.router, prefix="/api/v1")

