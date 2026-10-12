"""与 HTTP 框架无关的应用异常。

业务服务只表达“发生了什么”，由 API 层决定转换成 401、404、409 等 HTTP 状态。
这样业务服务未来可以被命令行任务、消息队列或 Agent 工具直接复用。
"""


class ApplicationError(Exception):
    code = "application_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuthenticationError(ApplicationError):
    code = "authentication_failed"


class ResourceNotFoundError(ApplicationError):
    code = "resource_not_found"


class ConflictError(ApplicationError):
    code = "resource_conflict"


class BusinessRuleError(ApplicationError):
    code = "business_rule_failed"

