"""FastAPI 的低基数 Prometheus 指标。

标签使用路由模板，例如 `/api/v1/orders/{order_id}`，避免把每个真实订单号创建成
独立时间序列。后续 Agent 节点、工具调用和模型 Token 指标也统一放在这里。
"""

from time import perf_counter

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


HTTP_REQUESTS = Counter(
    "mallmate_http_requests_total",
    "HTTP 请求总数",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "mallmate_http_request_duration_seconds",
    "HTTP 请求耗时",
    ("method", "route"),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(request.method, route_template, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route_template).observe(perf_counter() - started)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
