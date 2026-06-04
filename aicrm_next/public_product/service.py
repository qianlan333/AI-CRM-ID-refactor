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
    media = _render_detail_media(product)
    sections = _render_detail_sections(product)
    fallback = (
        f"""
      <section class="hero-panel">
        <div class="eyebrow">黄小璨 · 首月体验</div>
        <h1>{title}</h1>
        <p class="summary">{description or "面向新用户的轻量体验权益。"}</p>
        <dl class="product-specs">
          <div><dt>商品编码</dt><dd>{product_code}</dd></div>
          <div><dt>价格</dt><dd>{price}</dd></div>
          <div><dt>状态</dt><dd>{status}</dd></div>
        </dl>
      </section>
"""
        if not media
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · 商品详情</title>
  {_page_styles()}
</head>
<body class="product-body">
  <main class="product-page" data-route-owner="ai_crm_next" data-fallback-used="false" data-payment-request-executed="false" data-order-create-executed="false">
    {media}
    {fallback}
    {sections}
    <section class="safety-note">
      <strong>当前页面只展示商品信息</strong>
      <span>不创建订单，不发起真实支付。</span>
    </section>
  </main>
  <nav class="sticky-buy" aria-label="商品操作">
    <div>
      <div class="sticky-title">{title}</div>
      <div class="sticky-price"><small>{escape(str(product.get("currency") or "CNY"))}</small>{_price_amount(product)}</div>
    </div>
    <a class="cta" href="/pay/{product_code}">{cta}</a>
  </nav>
</body>
</html>"""


def render_pay_landing(product: dict[str, Any]) -> str:
    title = escape(str(product.get("title") or "支付入口"))
    price = format_price(product)
    product_code = escape(str(product.get("product_code") or ""))
    cta = escape(str(product.get("buy_button_text") or "立即报名"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · 支付入口</title>
  {_page_styles()}
</head>
<body class="product-body">
  <main class="product-page pay-page" data-route-owner="ai_crm_next" data-fallback-used="false" data-payment-request-executed="false" data-order-create-executed="false">
    <section class="hero-panel pay-panel">
      <div class="eyebrow">支付落地页</div>
      <h1>{title}</h1>
      <p class="summary">支付/下单动作已受控阻断，本页不会创建订单，也不会调用微信支付或支付宝。</p>
      <dl class="product-specs">
        <div><dt>商品编码</dt><dd>{product_code}</dd></div>
        <div><dt>价格</dt><dd>{price}</dd></div>
      </dl>
      <div class="pay-actions">
        <a class="secondary-link" href="/p/{product_code}">返回商品详情</a>
        <button class="disabled-pay" type="button" disabled>{cta} · 支付暂不可用</button>
      </div>
      <p class="quiet">不会创建订单，不会调用微信支付或支付宝。</p>
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


def _detail_image_source(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("image_url", "data_url", "url", "src"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
    return ""


def _detail_image_sources(product: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    for group_key in ("slices", "detail_images"):
        for item in list(product.get(group_key) or []):
            source = _detail_image_source(item)
            if source:
                sources.append(source)
    return sources


def _render_detail_media(product: dict[str, Any]) -> str:
    sources = _detail_image_sources(product)
    if not sources:
        return ""
    images = "\n".join(
        f'      <img class="slice-img" src="{escape(source, quote=True)}" loading="lazy" alt="">'
        for source in sources
    )
    return f"""
    <section class="detail-media" aria-label="商品详情图">
{images}
    </section>"""


def _render_detail_sections(product: dict[str, Any]) -> str:
    sections = []
    for item in list(product.get("detail_sections") or []):
        if not isinstance(item, dict):
            continue
        title = escape(str(item.get("title") or "").strip())
        body = escape(str(item.get("body") or item.get("content") or "").strip())
        if not title and not body:
            continue
        sections.append(
            f"""
      <article class="detail-card">
        {f"<h2>{title}</h2>" if title else ""}
        {f"<p>{body}</p>" if body else ""}
      </article>"""
        )
    if not sections:
        sections.append(
            """
      <article class="detail-card">
        <h2>服务说明</h2>
        <p>报名后请按页面指引完成后续联系与权益开通。</p>
      </article>"""
        )
    return "\n".join(["    <section class=\"detail-section\">", *sections, "    </section>"])


def _price_amount(product: dict[str, Any]) -> str:
    cents = int(product.get("price_cents") or 0)
    return f"{cents / 100:.2f}"


def format_price(product: dict[str, Any]) -> str:
    cents = int(product.get("price_cents") or 0)
    currency = str(product.get("currency") or "CNY").strip() or "CNY"
    return f"{currency} {cents / 100:.2f}"


def _page_styles() -> str:
    return """<style>
    :root {
      --ink: #17202a;
      --muted: #5f6b78;
      --line: #dbe5ee;
      --paper: #f7fbff;
      --panel: #fff;
      --gold: #ffc857;
      --gold-deep: #8a6200;
      --teal-soft: #e9f7f2;
      --teal-ink: #215a49;
      --shadow: 0 18px 46px rgba(24, 45, 68, .11);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body.product-body {
      background:
        linear-gradient(180deg, #f4fbff 0%, #fff 44%, #f7fbff 100%);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    .product-page {
      width: min(100%, 750px);
      min-height: 100vh;
      margin: 0 auto;
      padding-bottom: 104px;
      background: rgba(255, 255, 255, .86);
    }
    .detail-media { background: #fff; }
    .slice-img {
      display: block;
      width: 100%;
      min-height: 80px;
      background: #fff;
      object-fit: cover;
    }
    .hero-panel {
      margin: 18px 14px 12px;
      padding: 22px 18px 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, #fff 0%, var(--paper) 100%);
      box-shadow: var(--shadow);
    }
    .eyebrow {
      color: var(--gold-deep);
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 10px;
    }
    h1 {
      margin: 0;
      font-size: 44px;
      line-height: 1.08;
      font-weight: 950;
      letter-spacing: 0;
    }
    .summary {
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.65;
    }
    .product-specs {
      display: grid;
      gap: 10px;
      margin: 18px 0 0;
    }
    .product-specs div {
      display: grid;
      grid-template-columns: 88px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      padding: 12px 0;
      border-top: 1px solid rgba(234, 223, 206, .72);
    }
    .product-specs dt {
      color: var(--muted);
      font-size: 14px;
      font-weight: 800;
    }
    .product-specs dd {
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
      font-size: 17px;
      font-weight: 850;
    }
    .detail-section {
      display: grid;
      gap: 12px;
      padding: 0 14px 16px;
    }
    .detail-card {
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 30px rgba(20, 16, 10, .06);
    }
    .detail-card h2 {
      margin: 0 0 8px;
      font-size: 18px;
    }
    .detail-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      font-size: 15px;
      white-space: pre-wrap;
    }
    .safety-note {
      margin: 0 14px 18px;
      padding: 12px 14px;
      border-radius: 8px;
      background: var(--teal-soft);
      color: var(--teal-ink);
      font-size: 13px;
      line-height: 1.55;
    }
    .safety-note strong, .safety-note span { display: block; }
    .sticky-buy {
      position: fixed;
      left: 50%;
      bottom: 0;
      z-index: 20;
      transform: translateX(-50%);
      width: min(100%, 750px);
      padding: 10px 14px calc(12px + env(safe-area-inset-bottom));
      border-top: 1px solid rgba(236, 217, 184, .86);
      background: rgba(255, 253, 248, .96);
      backdrop-filter: blur(12px);
      box-shadow: 0 -12px 34px rgba(26, 32, 48, .12);
      display: grid;
      grid-template-columns: minmax(0, 1fr) 126px;
      gap: 12px;
      align-items: center;
    }
    .sticky-title {
      color: #44515d;
      font-size: 12px;
      font-weight: 900;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .sticky-price {
      margin-top: 3px;
      color: #9a6a00;
      font-size: 24px;
      font-weight: 950;
      line-height: 1;
    }
    .sticky-price small {
      margin-right: 4px;
      font-size: 12px;
      font-weight: 900;
    }
    .cta, .disabled-pay {
      height: 52px;
      border: 0;
      border-radius: 999px;
      background: var(--gold);
      color: #2a1c07;
      box-shadow: 0 8px 18px rgba(244, 179, 69, .34);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      font-size: 15px;
      font-weight: 950;
      white-space: nowrap;
    }
    .pay-page { display: grid; place-items: start center; padding-top: 18px; }
    .pay-panel { width: calc(100% - 28px); }
    .pay-actions {
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }
    .secondary-link {
      color: #6c3ca3;
      font-size: 15px;
      font-weight: 850;
    }
    .disabled-pay {
      width: 100%;
      color: rgba(42, 28, 7, .55);
      background: #eee5d5;
      box-shadow: none;
    }
    .disabled-pay:disabled { cursor: not-allowed; }
    .quiet {
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 420px) {
      .product-specs div { grid-template-columns: 74px minmax(0, 1fr); }
      h1 { font-size: 36px; }
      .sticky-buy { grid-template-columns: minmax(0, 1fr) 118px; }
      .cta, .disabled-pay { height: 50px; }
    }
  </style>"""
