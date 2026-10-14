"""登录账号、顾客关联与刷新会话的数据访问。"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuthSession, Customer, UserAccount


class UserRepository:
    """认证 Service 使用的数据库仓储。

    仓储只负责构造 SQL 和加入 ORM 对象，不在内部提交事务。登录、刷新轮换和退出
    是否属于同一事务，由上层 ``AuthService`` 决定。
    """

    def __init__(self, db: Session):
        self.db = db

    def get_account_by_username(self, username_normalized: str) -> UserAccount | None:
        return self.db.scalar(
            select(UserAccount).where(
                UserAccount.username_normalized == username_normalized
            )
        )

    def get_account_by_id(self, account_id: int) -> UserAccount | None:
        return self.db.get(UserAccount, account_id)

    def get_customer_by_account_id(self, account_id: int) -> Customer | None:
        """通过唯一外键找到账号对应的业务顾客资料。"""

        return self.db.scalar(
            select(Customer).where(Customer.user_account_id == account_id)
        )

    def add_session(self, session: AuthSession) -> None:
        self.db.add(session)

    def get_session_for_update(self, refresh_token_hash: str) -> AuthSession | None:
        """读取并锁定刷新会话，保证同一令牌只能成功轮换一次。

        PostgreSQL 会对命中的记录执行 ``FOR UPDATE``。本地 SQLite 会忽略行锁，
        所以并发认证流程应以 PostgreSQL 的行为作为正式环境基准。
        """

        statement = (
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == refresh_token_hash)
            .with_for_update()
        )
        return self.db.scalar(statement)

    def revoke_all_sessions(self, account_id: int, revoked_at: datetime) -> None:
        """撤销账号仍然有效的全部刷新会话。"""

        self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_account_id == account_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
