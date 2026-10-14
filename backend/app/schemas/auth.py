"""认证接口的请求和响应结构。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.common import APIModel


class LoginRequest(BaseModel):
    """账号密码登录请求。

    这里不继承带有 ``str_strip_whitespace`` 的 APIModel，因为空格可以是用户密码
    的合法组成部分；只对用户名去除首尾空白。
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=80)
    password: SecretStr = Field(min_length=8, max_length=256)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TokenResponse(APIModel):
    """登录或刷新成功后返回给前端的短期访问令牌。"""

    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0, description="访问令牌剩余有效秒数")


class CurrentUserResponse(APIModel):
    """前端恢复登录状态时使用的当前账号信息。"""

    account_id: int = Field(gt=0)
    username: str
    role: str
    customer_id: int | None


class LogoutResponse(APIModel):
    """退出接口的固定确认信息。"""

    message: str = "已退出登录"
