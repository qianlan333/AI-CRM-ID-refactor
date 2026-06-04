from __future__ import annotations

from html import escape
from typing import Any

from aicrm_next.commerce.domain import preview_product
from aicrm_next.commerce.repo import build_commerce_repository
from aicrm_next.shared.errors import NotFoundError


PUBLIC_PRODUCT_ROUTES = ("/p/{path:path}", "/pay/{path:path}", "/api/products/{path:path}")
PAYMENT_ACTION_SEGMENTS = {"checkout", "payment", "pay", "order", "orders", "jsapi", "notify", "return"}


def route_headers() -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "false",
        "X-AICRM-Payment-Request-Executed": "false",
        "X-AICRM-Order-Create-Executed": "false",
    }


def side_effect_safety() -> dict[str, bool]:
    return {
        "fallback_used": False,
        "real_external_call_executed": False,
        "payment_request_executed": False,
        "order_create_executed": False,
    }


def diagnostics_payload(route: str, *, allowed_methods: list[str]) -> dict[str, Any]:
    return {
        "ok": True,
        "route": route,
        "route_owner": "ai_crm_next",
        "source_status": "next_public_product",
        "allowed_methods": allowed_methods,
        **side_effect_safety(),
    }


def normalize_public_path(path: Any) -> str:
    normalized = str(path or "").strip().strip("/")
    if not normalized or "\\" in normalized or normalized.startswith(".") or "//" in normalized:
        raise NotFoundError("public product path not found")
    return normalized


def payment_action_detected(path: str) -> bool:
    segments = {segment.strip().lower() for segment in str(path or "").split("/") if segment.strip()}
    return bool(segments & PAYMENT_ACTION_SEGMENTS)


def get_public_product(path: Any) -> dict[str, Any]:
    normalized = normalize_public_path(path)
    if payment_action_detected(normalized):
        raise NotFoundError("public product path not found")
    repo = build_commerce_repository()
    product = repo.get_product_by_slug(normalized) or repo.get_product_by_code(normalized)
    if not product or not product.get("enabled"):
        raise NotFoundError("product not found")
    return preview_product(product)


def list_public_products(*, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    repo = build_commerce_repository()
    payload = repo.list_products(limit=limit, offset=offset)
    items = [preview_product(item) for item in payload.get("items") or [] if item.get("enabled")]
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "route_owner": "ai_crm_next",
        **side_effect_safety(),
    }


def public_product_payload(path: Any) -> dict[str, Any]:
    product = get_public_product(path)
    return {
        "ok": True,
        "product": product,
        "route_owner": "ai_crm_next",
        "source_status": "next_public_product_api",
        "checkout": blocked_checkout_payload(product),
        **side_effect_safety(),
    }


def blocked_checkout_payload(product: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "blocked",
        "message": "Public checkout/payment execution is blocked in this Legacy Exit group.",
        "next_route": f"/p/{product.get('product_code')}" if product else "",
        **side_effect_safety(),
    }


def blocked_action_payload(path: Any, *, method: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "public_product_payment_action_blocked",
        "error_code": "public_product_payment_action_blocked",
        "message": "This public product route only serves display/read contracts; checkout, payment, and order creation are out of scope.",
        "path": normalize_public_path(path),
        "method": method.upper(),
        "route_owner": "ai_crm_next",
        "source_status": "blocked_public_product_action",
        **side_effect_safety(),
    }


def product_not_found_payload(path: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "product_not_found",
        "error_code": "product_not_found",
        "message": "Public product path is not configured.",
        "path": str(path or "").strip().strip("/"),
        "route_owner": "ai_crm_next",
        **side_effect_safety(),
    }


def render_product_page(product: dict[str, Any]) -> str:
    title = escape(str(product.get("title") or "商品详情"))
    description = escape(str(product.get("description") or ""))
    price = format_price(product)
    status = "可查看" if product.get("enabled", True) else "不可购买"
    cta = escape(str(product.get("buy_button_text") or "查看商品"))
    product_code = escape(str(product.get("product_code") or ""))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · 商品详情</title>
</head>
<body>
  <main data-route-owner="ai_crm_next" data-fallback-used="false" data-payment-request-executed="false" data-order-create-executed="false">
    <section>
      <p>AI-CRM Next 商品页</p>
      <h1>{title}</h1>
      <p>{description}</p>
      <dl>
        <dt>商品编码</dt><dd>{product_code}</dd>
        <dt>价格</dt><dd>{price}</dd>
        <dt>状态</dt><dd>{status}</dd>
      </dl>
      <a href="/pay/{product_code}">{cta}</a>
      <p>当前页面只展示商品信息，不创建订单，不发起真实支付。</p>
    </section>
  </main>
</body>
</html>"""


def render_pay_landing(product: dict[str, Any]) -> str:
    title = escape(str(product.get("title") or "支付入口"))
    price = format_price(product)
    product_code = escape(str(product.get("product_code") or ""))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · 支付入口</title>
</head>
<body>
  <main data-route-owner="ai_crm_next" data-fallback-used="false" data-payment-request-executed="false" data-order-create-executed="false">
    <section>
      <p>AI-CRM Next 支付落地页</p>
      <h1>{title}</h1>
      <p>价格：{price}</p>
      <p>商品编码：{product_code}</p>
      <p>支付/下单动作已受控阻断，本页不会创建订单，也不会调用微信支付或支付宝。</p>
      <a href="/p/{product_code}">返回商品详情</a>
      <button type="button" disabled>支付暂不可用</button>
    </section>
  </main>
</body>
</html>"""


def render_not_found_page(path: Any) -> str:
    normalized = escape(str(path or "").strip().strip("/") or "-")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>商品不存在</title>
</head>
<body>
  <main data-route-owner="ai_crm_next" data-fallback-used="false">
    <h1>商品不存在</h1>
    <p>路径 {normalized} 未配置公开商品。</p>
  </main>
</body>
</html>"""


def format_price(product: dict[str, Any]) -> str:
    cents = int(product.get("price_cents") or 0)
    currency = str(product.get("currency") or "CNY").strip() or "CNY"
    return f"{currency} {cents / 100:.2f}"
