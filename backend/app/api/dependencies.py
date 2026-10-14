"""FastAPI 依赖装配。

这里负责把数据库会话、仓储和服务连接起来。路由只声明自己需要哪个服务，
不需要了解服务内部如何查询数据库。
"""

from collections.abc import Callable

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import UserRole
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import Principal
from app.db.session import get_db
from app.models import Customer, UserAccount
from app.repositories.after_sales import AfterSalesRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.customers import CustomerRepository
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.orders import OrderRepository
from app.repositories.users import UserRepository
from app.services.after_sales import AfterSalesService
from app.services.conversations import ConversationService
from app.services.identity import IdentityService
from app.services.knowledge import KnowledgeService
from app.services.orders import OrderService
from app.services.auth import AuthService


# 关闭 FastAPI 自动报错，让所有认证失败都使用项目统一的错误响应结构。
bearer_scheme = HTTPBearer(auto_error=False)


def get_identity_service(db: Session = Depends(get_db)) -> IdentityService:
    return IdentityService(CustomerRepository(db))


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """为一次请求装配认证服务；事务仍由 AuthService 的操作边界管理。"""

    return AuthService(db, UserRepository(db))


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(OrderRepository(db))


def get_knowledge_service(db: Session = Depends(get_db)) -> KnowledgeService:
    return KnowledgeService(KnowledgeRepository(db))


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    return ConversationService(db, ConversationRepository(db))


def get_after_sales_service(db: Session = Depends(get_db)) -> AfterSalesService:
    orders = OrderService(OrderRepository(db))
    return AfterSalesService(db, AfterSalesRepository(db), orders)


def _require_bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("缺少有效的访问令牌")
    return credentials.credentials


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
) -> UserAccount:
    """校验访问令牌，并重新查询账号状态。

    JWT 只证明令牌由本服务签发；账号是否已锁定或停用以当前数据库记录为准。
    """

    if not settings.auth_enabled:
        raise AuthenticationError("当前环境未启用正式认证")
    return auth.authenticate_access_token(_require_bearer_token(credentials))


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_demo_user: str = Header(default="demo-alice", alias="X-Demo-User"),
    auth: AuthService = Depends(get_auth_service),
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    """生成业务层和 Agent 共用的最小可信身份。

    正常开发配置必须使用 Bearer JWT。只有显式关闭正式认证并开启 ``demo_mode``
    时，才允许旧演示请求头，便于维护阶段短暂回退。
    """

    if settings.auth_enabled:
        return auth.principal_from_access_token(_require_bearer_token(credentials))

    if settings.demo_mode:
        customer = identity.get_demo_customer(x_demo_user)
        if customer.user_account_id is None:
            raise AuthenticationError("演示顾客尚未关联登录账号")
        return Principal(
            account_id=customer.user_account_id,
            role=UserRole.CUSTOMER.value,
            customer_id=customer.id,
        )

    raise AuthenticationError("当前环境未启用可用的身份认证方式")


def get_current_customer(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Customer:
    """要求当前账号是已关联顾客，并返回服务端确认的业务顾客资料。"""

    if principal.role != UserRole.CUSTOMER.value or principal.customer_id is None:
        raise AuthorizationError("当前账号没有顾客业务权限")

    customer = CustomerRepository(db).get_by_id(principal.customer_id)
    if customer is None or customer.user_account_id != principal.account_id:
        raise AuthenticationError("账号关联的顾客资料不存在")
    return customer


def require_role(*roles: UserRole | str) -> Callable[..., Principal]:
    """创建可复用的角色依赖，例如 ``Depends(require_role('admin'))``。"""

    allowed = {role.value if isinstance(role, UserRole) else role for role in roles}

    def check_role(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if principal.role not in allowed:
            raise AuthorizationError("当前账号没有访问该接口的权限")
        return principal

    return check_role

