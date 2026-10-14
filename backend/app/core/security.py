"""认证使用的密码、JWT 与可信身份工具。

本模块只处理密码和令牌等安全原语，不查询数据库，也不依赖 FastAPI。
账号是否存在、是否被停用以及资源是否属于当前用户，由 Service 层继续判断。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any
from uuid import uuid4

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from pydantic import SecretStr

from app.core.config import settings
from app.core.exceptions import AuthenticationError


# ``PasswordHash.recommended()`` 当前会选择 Argon2。算法参数由 pwdlib 维护，
# 后续升级依赖时可以通过 verify_and_update 平滑更新旧密码哈希。
_password_hash = PasswordHash.recommended()

# 当用户名不存在时仍执行一次真实的 Argon2 校验，缩小“账号存在”和“账号不存在”
# 两条路径之间的耗时差异。这里只在进程启动时生成一次虚假哈希。
_dummy_password_hash = _password_hash.hash("mallmate-dummy-password-never-used")

# 第一版只允许基于共享密钥的 HMAC 算法。算法列表由服务端固定，不能采用 JWT
# 头部中由客户端提供的算法，从而避免算法降级或 ``alg=none`` 一类问题。
_SUPPORTED_JWT_ALGORITHMS = frozenset({"HS256"})


@dataclass(frozen=True)
class Principal:
    """一次请求中已经通过后端认证的可信身份。

    ``Principal`` 只能由认证服务根据 JWT 和数据库记录生成。请求体、URL 参数、
    聊天文本和大模型输出都不能直接构造或覆盖这个对象。
    """

    account_id: int
    role: str
    customer_id: int | None


def hash_password(password: str) -> str:
    """使用 Argon2 对新密码做不可逆哈希。"""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """验证密码；格式损坏的哈希统一按验证失败处理。

    不把底层库的异常直接返回给调用方，避免泄露数据库中哈希的具体状态。
    """

    encoded_hash = password_hash or _dummy_password_hash
    try:
        return _password_hash.verify(password, encoded_hash)
    except (PwdlibError, TypeError, ValueError):
        return False


def verify_dummy_password(password: str) -> None:
    """为不存在的账号执行等价的 Argon2 工作量。

    返回值没有业务意义；这个函数只用于减小用户名枚举所依赖的时间差异。
    """

    verify_password(password, _dummy_password_hash)


def create_access_token(account_id: int) -> str:
    """为已认证账号签发短期访问 JWT。

    JWT 只保存账号 ID 和标准校验声明，不放入手机号、地址、密码或 API Key。
    角色和账号状态会在每次请求时从数据库重新读取，停用账号后无需等待角色信息
    在令牌中过期。
    """

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(account_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        _jwt_secret(),
        algorithm=_jwt_algorithm(),
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """验证访问 JWT，并返回已经验证过的声明。

    签名错误、过期、签发者错误、受众错误和缺少必要声明，对外都表现为同一个
    ``AuthenticationError``，防止把令牌验证细节暴露给客户端。
    """

    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[_jwt_algorithm()],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "iss", "aud", "iat", "exp", "jti"]},
        )
    except (InvalidTokenError, TypeError, ValueError):
        raise AuthenticationError("访问令牌无效或已过期") from None

    # PyJWT 会校验声明是否存在，但 ``sub`` 的业务格式仍需应用自己检查。
    try:
        account_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise AuthenticationError("访问令牌无效或已过期") from None
    if account_id <= 0:
        raise AuthenticationError("访问令牌无效或已过期")

    return payload


def access_token_account_id(token: str) -> int:
    """从通过完整校验的访问 JWT 中取得账号 ID。"""

    return int(decode_access_token(token)["sub"])


def generate_refresh_token() -> str:
    """生成高熵、不承载业务数据的刷新令牌原文。

    令牌原文只会写入 HttpOnly Cookie；数据库只保存下面函数生成的摘要。
    """

    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    """生成用于数据库等值查询的刷新令牌摘要。

    刷新令牌本身具有足够高的随机熵，因此这里使用 SHA-256 做不可逆索引即可；
    它与低熵用户密码不同，不需要使用慢速密码哈希。
    """

    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def _jwt_algorithm() -> str:
    """返回配置中的固定算法，并拒绝第一版没有审核过的算法。"""

    algorithm = settings.jwt_algorithm.upper()
    if algorithm not in _SUPPORTED_JWT_ALGORITHMS:
        raise RuntimeError(f"不支持的 JWT 签名算法：{algorithm}")
    return algorithm


def _jwt_secret() -> str:
    """安全地从 Settings 读取 JWT 密钥，不在异常中打印密钥内容。"""

    configured = settings.jwt_secret
    secret = (
        configured.get_secret_value()
        if isinstance(configured, SecretStr)
        else str(configured)
    )
    if not secret:
        raise RuntimeError("启用认证前必须配置 MALLMATE_JWT_SECRET")
    return secret
