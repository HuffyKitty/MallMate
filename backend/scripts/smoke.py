"""对运行中的演示 API 做一轮有业务意义的冒烟检查。"""

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:18080"


def call(path: str, user: str = "demo-alice", payload: dict | None = None, key: str | None = None):
    headers = {"X-Demo-User": user}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if key:
        headers["Idempotency-Key"] = key
    request = Request(BASE + path, data=body, headers=headers, method="POST" if payload else "GET")
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def main() -> None:
    assert call("/health")[0] == 200
    status, faq = call("/api/v1/chat", payload={"message": "退货上门取件要多久"})
    assert status == 200 and faq["sources"] and faq["intent"] == "policy_faq", faq
    status, order = call("/api/v1/orders/1001")
    assert status == 200 and order["status"] == "delivered", order
    assert call("/api/v1/orders/2001")[0] == 404
    assert call("/api/v1/orders/1001", user="demo-bob")[0] == 404
    payload = {"order_id": 1001, "case_type": "return", "reason": "灯罩收到时有裂纹"}
    status, preview = call("/api/v1/after-sales/preview", payload=payload)
    assert status == 200 and preview["eligible"], preview
    status, denied = call("/api/v1/after-sales/preview", payload={**payload, "order_id": 1002})
    assert status == 200 and not denied["eligible"], denied
    confirm = {**payload, "confirmed": True}
    status, first = call("/api/v1/after-sales/confirm", payload=confirm, key="smoke-case-1001")
    assert status == 200 and first["status"] == "pending_review", first
    status, second = call("/api/v1/after-sales/confirm", payload=confirm, key="smoke-case-1001")
    assert status == 200 and second["case_id"] == first["case_id"], second
    print("PASS: health, FAQ source, order ownership, eligibility, confirmed write, idempotency")


if __name__ == "__main__":
    main()

