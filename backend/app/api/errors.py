"""把领域异常统一转换成 HTTP 响应。"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
)


STATUS_BY_ERROR = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
    ResourceNotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    BusinessRuleError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def register_exception_handlers(app: FastAPI) -> None:
    """注册一次全局处理器，让所有路由获得一致的错误结构。"""

    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        _: Request, exc: ApplicationError
    ) -> JSONResponse:
        status_code = STATUS_BY_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if isinstance(exc, AuthenticationError)
            else None
        )
        return JSONResponse(
            status_code=status_code,
            content={"code": exc.code, "detail": exc.message},
            headers=headers,
        )

