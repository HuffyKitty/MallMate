"""多个接口复用的响应结构。"""

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """API 模型基类：自动去除字符串首尾空白，并拒绝未声明字段。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class SourceResponse(APIModel):
    title: str
    version: str
    uri: str


class ErrorResponse(APIModel):
    code: str
    detail: str

