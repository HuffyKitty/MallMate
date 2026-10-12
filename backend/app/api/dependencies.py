"""FastAPI 依赖装配。

这里负责把数据库会话、仓储和服务连接起来。路由只声明自己需要哪个服务，
不需要了解服务内部如何查询数据库。
"""

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.db.session import get_db
from app.models import Customer
from app.repositories.after_sales import AfterSalesRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.customers import CustomerRepository
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.orders import OrderRepository
from app.services.after_sales import AfterSalesService
from app.services.conversations import ConversationService
from app.services.identity import IdentityService
from app.services.knowledge import KnowledgeService
from app.services.orders import OrderService


def get_identity_service(db: Session = Depends(get_db)) -> IdentityService:
    return IdentityService(CustomerRepository(db))


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(OrderRepository(db))


def get_knowledge_service(db: Session = Depends(get_db)) -> KnowledgeService:
    return KnowledgeService(KnowledgeRepository(db))


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    return ConversationService(db, ConversationRepository(db))


def get_after_sales_service(db: Session = Depends(get_db)) -> AfterSalesService:
    orders = OrderService(OrderRepository(db))
    return AfterSalesService(db, AfterSalesRepository(db), orders)


def current_customer(
    x_demo_user: str = Header(default="demo-alice", alias="X-Demo-User"),
    identity: IdentityService = Depends(get_identity_service),
) -> Customer:
    """把演示请求头转换成可信的数据库用户对象。

    正式认证接入后只需替换这个依赖，业务路由仍然接收 Customer。
    """

    if not settings.demo_mode:
        raise AuthenticationError("当前环境尚未配置正式认证")
    return identity.get_demo_customer(x_demo_user)

