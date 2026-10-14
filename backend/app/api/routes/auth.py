"""账号登录、令牌刷新、退出和当前账号接口。"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.session import get_db
from app.repositories.users import UserRepository
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LogoutResponse,
    TokenResponse,
)
from app.services.auth import AuthService, IssuedCredentials


router = APIRouter(prefix="/auth", tags=["auth"])

# ``auto_error=False`` 让缺少或格式错误的 Authorization 头也走项目统一的
# AuthenticationError 响应结构，而不是由 FastAPI 生成另一种错误格式。
_bearer = HTTPBearer(auto_error=False)


def _get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """为单次 HTTP 请求装配认证服务与仓储。"""

    return AuthService(db, UserRepository(db))


def _get_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """从标准 Bearer 头中提取访问令牌。"""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("缺少有效的访问令牌")
    return credentials.credentials


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """验证账号密码，把刷新令牌写入 HttpOnly Cookie。"""

    _validate_request_origin(http_request)
    credentials = auth.login(request.username, request.password.get_secret_value())
    _set_refresh_cookie(response, credentials)
    _disable_token_response_cache(response)
    return _token_response(credentials)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """使用 Cookie 中的刷新令牌完成一次性轮换。"""

    _validate_request_origin(request)
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise AuthenticationError("缺少刷新令牌")

    credentials = auth.refresh(refresh_token)
    _set_refresh_cookie(response, credentials)
    _disable_token_response_cache(response)
    return _token_response(credentials)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    auth: AuthService = Depends(_get_auth_service),
) -> LogoutResponse:
    """撤销当前刷新会话，并删除浏览器中的刷新 Cookie。"""

    _validate_request_origin(request)
    auth.logout(request.cookies.get(settings.refresh_cookie_name))
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    _disable_token_response_cache(response)
    return LogoutResponse()


@router.get("/me", response_model=CurrentUserResponse)
def me(
    response: Response,
    access_token: str = Depends(_get_access_token),
    auth: AuthService = Depends(_get_auth_service),
) -> CurrentUserResponse:
    """返回前端恢复登录状态所需的最小身份信息。"""

    account = auth.authenticate_access_token(access_token)
    principal = auth.build_principal(account)
    _disable_token_response_cache(response)
    return CurrentUserResponse(
        account_id=account.id,
        username=account.username_normalized,
        role=principal.role,
        customer_id=principal.customer_id,
    )


def _set_refresh_cookie(response: Response, credentials: IssuedCredentials) -> None:
    """以浏览器脚本不可读的方式保存刷新令牌。"""

    max_age = settings.refresh_token_days * 24 * 60 * 60
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=credentials.refresh_token,
        max_age=max_age,
        path=settings.refresh_cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _validate_request_origin(request: Request) -> None:
    """拒绝浏览器从未授权来源携带刷新 Cookie 调用状态接口。

    非浏览器客户端可能不发送 Origin，因此只在该头存在时做精确匹配。正式公网
    部署若允许跨站前端，还应在此基础上增加独立 CSRF Token。
    """

    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        raise AuthorizationError("请求来源不受信任")


def _disable_token_response_cache(response: Response) -> None:
    """阻止代理或浏览器缓存包含访问令牌的响应。"""

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _token_response(credentials: IssuedCredentials) -> TokenResponse:
    return TokenResponse(
        access_token=credentials.access_token,
        expires_in=credentials.expires_in,
    )
