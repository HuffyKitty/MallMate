"""演示身份服务；后续正式认证只需替换这一层和 API 依赖。"""

from app.core.exceptions import AuthenticationError
from app.models import Customer
from app.repositories.customers import CustomerRepository


class IdentityService:
    def __init__(self, customers: CustomerRepository):
        self.customers = customers

    def get_demo_customer(self, handle: str) -> Customer:
        customer = self.customers.get_by_demo_handle(handle)
        if customer is None:
            raise AuthenticationError("演示用户不存在")
        return customer

