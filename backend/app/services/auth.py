"""登录、访问令牌认证、刷新轮换和退出登录服务。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import unicodedata
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    Principal,
    access_token_account_id,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_dummy_password,
    verify_password,
)
from app.models import AuthSession, UserAccount
from app.repositories.users import UserRepository


@dataclass(frozen=True)
class IssuedCredentials:
    """Service 层生成的一组令牌。

    ``refresh_token`` 只能交给路由写入 HttpOnly Cookie，不能进入 JSON 响应、日志
    或 LangGraph State。
    """

    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    """认证业务编排。

    访问 JWT 负责证明请求持有有效签名；数据库中的账号状态和顾客关联负责决定该
    身份当前是否仍可使用。刷新令牌轮换在同一个数据库事务中完成。
    """

    def __init__(self, db: Session, users: UserRepository):
        self.db = db
        self.users = users

    def login(self, username: str, password: str) -> IssuedCredentials:
        """验证账号密码，创建刷新会话，并签发短期访问 JWT。"""

        self._ensure_auth_enabled()
        normalized = normalize_username(username)
        account = self.users.get_account_by_username(normalized)

        if account is None:
            # 即使账号不存在也执行 Argon2，避免响应时间明显暴露用户名是否存在。
            verify_dummy_password(password)
            raise self._invalid_credentials()

        if not verify_password(password, account.password_hash):
            raise self._invalid_credentials()
        if not self._is_active(account):
            # 对登录调用方保持统一错误，不泄露账号是锁定还是停用。
            raise self._invalid_credentials()

        credentials = self._issue_credentials(account)
        self.db.commit()
        return credentials

    def refresh(self, refresh_token: str) -> IssuedCredentials:
        """原子撤销旧刷新会话，并签发一组全新的令牌。"""

        self._ensure_auth_enabled()
        now = datetime.now(timezone.utc)
        token_hash = hash_refresh_token(refresh_token)
        session = self.users.get_session_for_update(token_hash)
        if session is None or session.revoked_at is not None:
            raise self._invalid_refresh_token()

        # SQLite 可能返回不带时区的 datetime；统一补成 UTC 后再比较。
        if _as_utc(session.expires_at) <= now:
            session.revoked_at = now
            self.db.commit()
            raise self._invalid_refresh_token()

        account = self.users.get_account_by_id(session.user_account_id)
        if account is None or not self._is_active(account):
            session.revoked_at = now
            self.db.commit()
            raise self._invalid_refresh_token()

        # 密码修改后的旧刷新会话不能继续使用。正常的改密流程还应主动调用
        # revoke_all_sessions；这里是额外的纵深校验。
        if account.password_changed_at is not None and (
            _as_utc(session.created_at) < _as_utc(account.password_changed_at)
        ):
            session.revoked_at = now
            self.db.commit()
            raise self._invalid_refresh_token()

        session.revoked_at = now
        credentials = self._issue_credentials(account, issued_at=now)
        self.db.commit()
        return credentials

    def logout(self, refresh_token: str | None) -> None:
        """撤销当前刷新会话；无 Cookie 或重复退出也视为成功。"""

        if not refresh_token:
            return

        session = self.users.get_session_for_update(hash_refresh_token(refresh_token))
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            self.db.commit()

    def revoke_all_sessions(self, account_id: int) -> None:
        """供停用账号或修改密码流程撤销全部刷新会话。"""

        self.users.revoke_all_sessions(account_id, datetime.now(timezone.utc))
        self.db.commit()

    def authenticate_access_token(self, token: str) -> UserAccount:
        """校验 JWT，并返回数据库中当前仍有效的账号。

        返回 ``UserAccount`` 便于 FastAPI 依赖复用；需要传给 Agent 或业务服务时，
        应继续调用 ``build_principal``，转换为字段更少的只读可信身份。
        """

        self._ensure_auth_enabled()
        account_id = access_token_account_id(token)
        account = self.users.get_account_by_id(account_id)
        if account is None or not self._is_active(account):
            raise AuthenticationError("账号不存在或已停用")
        return account

    def build_principal(self, account: UserAccount) -> Principal:
        """根据已认证账号及顾客关联生成 Agent 可用的可信身份。"""

        customer = self.users.get_customer_by_account_id(account.id)
        customer_id = customer.id if customer is not None else None
        role = _enum_value(account.role)
        if role == "customer" and customer_id is None:
            raise AuthenticationError("顾客账号尚未关联顾客资料")
        return Principal(account_id=account.id, role=role, customer_id=customer_id)

    def principal_from_access_token(self, token: str) -> Principal:
        """一步完成访问令牌认证和可信身份构造。"""

        return self.build_principal(self.authenticate_access_token(token))

    def _issue_credentials(
        self,
        account: UserAccount,
        *,
        issued_at: datetime | None = None,
    ) -> IssuedCredentials:
        """创建刷新会话 ORM 对象；提交事务由调用方负责。"""

        now = issued_at or datetime.now(timezone.utc)
        refresh_token = generate_refresh_token()
        refresh_expires_at = now + timedelta(days=settings.refresh_token_days)
        self.users.add_session(
            AuthSession(
                id=str(uuid4()),
                user_account_id=account.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                created_at=now,
                expires_at=refresh_expires_at,
                revoked_at=None,
            )
        )
        return IssuedCredentials(
            access_token=create_access_token(account.id),
            refresh_token=refresh_token,
            expires_in=settings.access_token_minutes * 60,
        )

    @staticmethod
    def _is_active(account: UserAccount) -> bool:
        return _enum_value(account.status) == "active"

    @staticmethod
    def _invalid_credentials() -> AuthenticationError:
        return AuthenticationError("用户名或密码错误")

    @staticmethod
    def _invalid_refresh_token() -> AuthenticationError:
        return AuthenticationError("刷新令牌无效或已过期")

    @staticmethod
    def _ensure_auth_enabled() -> None:
        if not settings.auth_enabled:
            raise AuthenticationError("当前环境未启用正式认证")


def normalize_username(username: str) -> str:
    """统一用户名大小写与 Unicode 表示，必须与建号流程使用同一规则。"""

    return unicodedata.normalize("NFKC", username).strip().casefold()


def _as_utc(value: datetime) -> datetime:
    """把数据库读出的时间统一转换为带 UTC 时区的 datetime。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _enum_value(value: object) -> str:
    """同时兼容数据库字符串和后续可能采用的 ``StrEnum``。"""

    raw = getattr(value, "value", value)
    return str(raw)
