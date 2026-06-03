from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import assert_repository_allowed

from .domain import normalize_status, now_iso, validate_price_cents, validate_product_code


class CommerceRepository(Protocol):
    def list_products(self, *, limit: int, offset: int) -> dict[str, Any]: ...
    def get_product(self, product_id: str) -> dict[str, Any] | None: ...
    def get_product_by_code(self, product_code: str) -> dict[str, Any] | None: ...
    def get_product_by_slug(self, page_slug: str) -> dict[str, Any] | None: ...
    def save_product(self, payload: dict[str, Any], product_id: str | None = None) -> dict[str, Any]: ...
    def set_product_enabled(self, product_id: str, enabled: bool) -> dict[str, Any]: ...
    def delete_product(self, product_id: str) -> dict[str, Any]: ...
    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_order(self, order_no: str) -> dict[str, Any] | None: ...
    def apply_notify(self, order_no: str, provider: str, status: str, transaction_id: str | None) -> dict[str, Any]: ...
    def list_transactions(self, provider: str, filters: dict[str, Any], *, limit: int, offset: int) -> dict[str, Any]: ...
    def request_refund(self, provider: str, order_no: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def _seed_products() -> list[dict[str, Any]]:
    ts = "2026-05-20T12:00:00Z"
    return [
        {
            "id": "prod_001",
            "product_code": "course_masked_001",
            "title": "课程商品样例",
            "description": "AI-CRM Next fixture 商品，不生成真实支付。",
            "price_cents": 9900,
            "currency": "CNY",
            "enabled": True,
            "page_slug": "course-masked-001",
            "cover_image_id": "image_masked_001",
            "detail_image_ids": ["image_masked_001"],
            "detail_sections": [{"title": "商品详情", "body": "脱敏 fixture 内容"}],
            "buy_button_text": "立即购买",
            "created_at": ts,
            "updated_at": ts,
            "deleted": False,
        },
        {
            "id": "prod_002",
            "product_code": "course_disabled_001",
            "title": "已下架商品样例",
            "description": "用于 disabled checkout 契约。",
            "price_cents": 19900,
            "currency": "CNY",
            "enabled": False,
            "page_slug": "course-disabled-001",
            "cover_image_id": "image_masked_001",
            "detail_image_ids": [],
            "detail_sections": [],
            "buy_button_text": "暂不可购买",
            "created_at": ts,
            "updated_at": ts,
            "deleted": False,
        },
    ]


def _seed_orders() -> list[dict[str, Any]]:
    ts = "2026-05-20T12:01:00Z"
    return [
        {
            "order_no": "order_masked_001",
            "payment_provider": "wechat",
            "product_code": "course_masked_001",
            "product_title": "课程商品样例",
            "buyer_mobile": "mobile_masked_001",
            "external_userid": "external_user_masked_001",
            "amount_cents": 9900,
            "currency": "CNY",
            "payment_status": "paid",
            "transaction_id": "transaction_masked_001",
            "refunded_amount_total": 0,
            "active_refund_amount_total": 0,
            "refund_status": "",
            "paid_at": ts,
            "created_at": ts,
            "updated_at": ts,
            "quantity": 1,
        }
    ]


class InMemoryCommerceRepository:
    def __init__(self, products: list[dict[str, Any]] | None = None, orders: list[dict[str, Any]] | None = None) -> None:
        self._products = deepcopy(products if products is not None else _seed_products())
        self._orders = deepcopy(orders if orders is not None else _seed_orders())

    def list_products(self, *, limit: int, offset: int) -> dict[str, Any]:
        rows = [deepcopy(item) for item in self._products if not item.get("deleted")]
        return {"items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        return self._find_product(lambda item: item["id"] == product_id)

    def get_product_by_code(self, product_code: str) -> dict[str, Any] | None:
        return self._find_product(lambda item: item["product_code"] == product_code)

    def get_product_by_slug(self, page_slug: str) -> dict[str, Any] | None:
        return self._find_product(lambda item: item["page_slug"] == page_slug)

    def save_product(self, payload: dict[str, Any], product_id: str | None = None) -> dict[str, Any]:
        validate_price_cents(int(payload.get("price_cents", 0)))
        now = now_iso()
        code = validate_product_code(str(payload["product_code"]))
        payload = {**payload, "product_code": code}
        existing = self.get_product_by_code(code)
        if existing and existing["id"] != product_id:
            raise ContractError("product_code must be unique")
        if product_id:
            for index, item in enumerate(self._products):
                if item["id"] == product_id and not item.get("deleted"):
                    updated = {**item, **payload, "id": product_id, "updated_at": now}
                    self._products[index] = updated
                    return deepcopy(updated)
            raise NotFoundError("product not found")
        product = {
            **payload,
            "id": f"prod_{len(self._products) + 1:03d}",
            "page_slug": payload.get("page_slug") or code,
            "created_at": now,
            "updated_at": now,
            "deleted": False,
        }
        self._products.append(product)
        return deepcopy(product)

    def set_product_enabled(self, product_id: str, enabled: bool) -> dict[str, Any]:
        product = self.get_product(product_id)
        if not product:
            raise NotFoundError("product not found")
        product["enabled"] = enabled
        return self.save_product(product, product_id)

    def delete_product(self, product_id: str) -> dict[str, Any]:
        for item in self._products:
            if item["id"] == product_id and not item.get("deleted"):
                item["deleted"] = True
                item["enabled"] = False
                item["updated_at"] = now_iso()
                return {"ok": True, "deleted": True, "soft_deleted": True, "product_id": product_id}
        raise NotFoundError("product not found")

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        order = {
            **payload,
            "order_no": f"order_fake_{len(self._orders) + 1:04d}",
            "payment_status": "pending",
            "transaction_id": "",
            "paid_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self._orders.append(order)
        return deepcopy(order)

    def get_order(self, order_no: str) -> dict[str, Any] | None:
        for order in self._orders:
            if order["order_no"] == order_no:
                return deepcopy(order)
        return None

    def apply_notify(self, order_no: str, provider: str, status: str, transaction_id: str | None) -> dict[str, Any]:
        next_status = normalize_status(status)
        for order in self._orders:
            if order["order_no"] == order_no:
                if order["payment_provider"] != provider:
                    raise ContractError("payment_provider mismatch")
                if order["payment_status"] == next_status and order.get("transaction_id"):
                    return deepcopy(order)
                order["payment_status"] = next_status
                order["transaction_id"] = transaction_id or order.get("transaction_id") or f"transaction_fake_{order_no}"
                order.setdefault("refunded_amount_total", 0)
                order.setdefault("active_refund_amount_total", 0)
                order.setdefault("refund_status", "")
                order["paid_at"] = now_iso() if next_status == "paid" else order.get("paid_at")
                order["updated_at"] = now_iso()
                return deepcopy(order)
        raise NotFoundError("order not found")

    def list_transactions(self, provider: str, filters: dict[str, Any], *, limit: int, offset: int) -> dict[str, Any]:
        rows = [deepcopy(order) for order in self._orders if order["payment_provider"] == provider]
        for key in ["payment_status", "product_code", "external_userid"]:
            if filters.get(key):
                rows = [row for row in rows if row.get(key) == filters[key]]
        if filters.get("mobile"):
            rows = [row for row in rows if filters["mobile"] in str(row.get("buyer_mobile") or "")]
        if filters.get("date_from"):
            rows = [row for row in rows if str(row.get("created_at") or "") >= filters["date_from"]]
        if filters.get("date_to"):
            rows = [row for row in rows if str(row.get("created_at") or "") <= filters["date_to"]]
        return {"items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    def request_refund(self, provider: str, order_no: str, payload: dict[str, Any]) -> dict[str, Any]:
        for order in self._orders:
            if order["order_no"] == order_no:
                if order["payment_provider"] != provider:
                    raise ContractError("payment_provider mismatch")
                active = int(order.get("active_refund_amount_total") or 0)
                order["active_refund_amount_total"] = active + int(payload.get("refund_amount_total") or 0)
                order["refund_status"] = "requested"
                order["updated_at"] = now_iso()
                return {
                    "refund": {
                        "status": "requested",
                        "status_label": "退款申请已提交",
                        "out_refund_no": payload.get("out_refund_no", ""),
                    },
                    "order": deepcopy(order),
                }
        raise NotFoundError("order not found")

    def _find_product(self, predicate) -> dict[str, Any] | None:
        for item in self._products:
            if predicate(item) and not item.get("deleted"):
                return deepcopy(item)
        return None


_GLOBAL_REPO = InMemoryCommerceRepository()


def build_commerce_repository() -> CommerceRepository:
    return assert_repository_allowed(_GLOBAL_REPO, capability_owner="commerce")


def reset_commerce_fixture_state() -> None:
    global _GLOBAL_REPO
    _GLOBAL_REPO = InMemoryCommerceRepository()
