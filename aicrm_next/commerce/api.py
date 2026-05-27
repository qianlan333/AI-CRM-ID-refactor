from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.shared.errors import ContractError, NotFoundError

from .admin_transactions import (
    default_filters,
    export_orders_csv,
    get_wechat_admin_order,
    list_wechat_admin_orders,
    list_wechat_product_options,
)
from .application import (
    CheckoutCommand,
    DeleteProductCommand,
    GetOrderQuery,
    GetProductQuery,
    GetPublicProductQuery,
    GetTransactionQuery,
    ListProductsQuery,
    ListTransactionsQuery,
    NotifyPaymentCommand,
    PaymentReturnCommand,
    SetProductEnabledCommand,
    UpsertProductCommand,
)
from .dto import CheckoutRequest, PaymentNotifyRequest, ProductUpsertRequest

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/wechat-pay/transactions", response_class=HTMLResponse, name="api.admin_wechat_pay_transactions_page")
def admin_wechat_transactions_page(request: Request):
    return templates.TemplateResponse(
        request,
        "wechat_transactions.html",
        {
            "request": request,
            "default_filters": default_filters(),
            "product_options": list_wechat_product_options(),
        },
    )


@router.get("/admin/wechat-pay/transactions/{order_id}", response_class=HTMLResponse, name="api.admin_wechat_pay_transaction_detail_page")
def admin_wechat_transaction_detail_page(order_id: str) -> Response:
    order = get_wechat_admin_order(order_id)
    if not order:
        return HTMLResponse(
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>订单不存在</title></head>"
            "<body><main><h1>订单不存在</h1><p><a href='/admin/wechat-pay/transactions'>返回交易管理</a></p></main></body></html>",
            status_code=404,
        )
    fields = [
        ("微信单号", order["transaction_id"]),
        ("订单创建时间", order["created_at"]),
        ("付款人", order["payer_name"]),
        ("手机号", order.get("mobile") or "未记录"),
        ("客户身份", order.get("userid") or order.get("external_userid") or "-"),
        ("商品", f"{order['product_name']} / {order['product_code']}"),
        ("金额", f"¥{order['amount_yuan']} {order['currency']}"),
        ("状态", order["status_label"]),
    ]
    rows = "".join(
        f"<div class='label'>{html.escape(str(label))}</div><div class='value'>{html.escape(str(value))}</div>"
        for label, value in fields
    )
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>微信支付订单详情</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f7fb;color:#172033;margin:0}"
        "main{max-width:760px;margin:48px auto;background:#fff;border:1px solid #dbe5f3;border-radius:8px;padding:28px}"
        ".grid{display:grid;grid-template-columns:140px 1fr;gap:12px 16px;margin:22px 0}.label{color:#66758a;font-weight:800}"
        ".value{font-weight:900;word-break:break-all}a{color:#2563eb;font-weight:800;text-decoration:none}</style></head><body><main>"
        "<h1>微信支付订单详情</h1>"
        "<p>详情读模型由 AI-CRM Next commerce 提供。</p>"
        f"<div class='grid'>{rows}</div>"
        "<p><a href='/admin/wechat-pay/transactions'>返回交易管理</a></p>"
        "</main></body></html>"
    )


@router.get("/api/admin/wechat-pay/orders")
def list_wechat_admin_order_page(
    mobile: str | None = None,
    identity: str | None = None,
    transaction_id: str | None = None,
    product_code: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    return list_wechat_admin_orders(
        {
            "mobile": mobile,
            "identity": identity,
            "transaction_id": transaction_id,
            "product_code": product_code,
            "created_from": created_from,
            "created_to": created_to,
            "status": status,
        },
        limit=limit,
        offset=offset,
    )


@router.post("/api/admin/wechat-pay/order-exports")
async def export_wechat_admin_orders(request: Request) -> Response:
    payload = await request.json()
    csv_text = export_orders_csv(payload.get("filters") if isinstance(payload, dict) else {})
    return Response(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="wechat-pay-orders.csv"'},
    )


@router.get("/api/admin/wechat-pay/products")
def list_products(limit: int = 50, offset: int = 0) -> dict:
    return ListProductsQuery()(limit=limit, offset=offset)


@router.get("/api/admin/wechat-pay/products/{product_id}")
def get_product(product_id: str) -> dict:
    try:
        return GetProductQuery()(product_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/wechat-pay/products")
def create_product(payload: ProductUpsertRequest) -> dict:
    try:
        return UpsertProductCommand()(payload)
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/wechat-pay/products/{product_id}")
def update_product(product_id: str, payload: ProductUpsertRequest) -> dict:
    try:
        return UpsertProductCommand()(payload, product_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/wechat-pay/products/{product_id}/enable")
def enable_product(product_id: str) -> dict:
    try:
        return SetProductEnabledCommand()(product_id, enabled=True)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/wechat-pay/products/{product_id}/disable")
def disable_product(product_id: str) -> dict:
    try:
        return SetProductEnabledCommand()(product_id, enabled=False)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/wechat-pay/products/{product_id}")
def delete_product(product_id: str) -> dict:
    try:
        return DeleteProductCommand()(product_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/products/{page_slug}")
def public_product(page_slug: str) -> dict:
    try:
        return GetPublicProductQuery()(page_slug)
    except Exception as exc:
        _raise_http(exc)


@router.get("/p/{page_slug}", response_class=HTMLResponse)
def product_page(request: Request, page_slug: str) -> str:
    try:
        payload = GetPublicProductQuery()(page_slug)
    except Exception as exc:
        _raise_http(exc)
    product = payload["product"]
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + product["title"]
        + "</title></head><body><main><h1>"
        + product["title"]
        + "</h1><p>"
        + product.get("description", "")
        + "</p><button>"
        + product.get("buy_button_text", "立即购买")
        + "</button></main></body></html>"
    )


@router.post("/api/checkout/wechat")
def checkout_wechat(payload: CheckoutRequest) -> dict:
    try:
        return CheckoutCommand("wechat")(payload)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/checkout/alipay")
def checkout_alipay(payload: CheckoutRequest) -> dict:
    try:
        return CheckoutCommand("alipay")(payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/orders/{order_no}")
@router.get("/api/orders/{order_no}/status")
def get_order(order_no: str) -> dict:
    try:
        return GetOrderQuery()(order_no)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/wechat-pay/notify")
def wechat_notify(payload: PaymentNotifyRequest) -> dict:
    try:
        return NotifyPaymentCommand("wechat")(payload)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/alipay/notify")
def alipay_notify(payload: PaymentNotifyRequest) -> dict:
    try:
        return NotifyPaymentCommand("alipay")(payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/alipay/return")
def alipay_return(order_no: str = "", status: str = "paid") -> dict:
    try:
        return PaymentReturnCommand()(order_no=order_no, status=status)
    except Exception as exc:
        _raise_http(exc)


def _transaction_filters(
    payment_status: str | None = None,
    product_code: str | None = None,
    mobile: str | None = None,
    external_userid: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    return {
        "payment_status": payment_status,
        "product_code": product_code,
        "mobile": mobile,
        "external_userid": external_userid,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get("/api/admin/wechat-pay/transactions")
def list_wechat_transactions(
    payment_status: str | None = None,
    product_code: str | None = None,
    mobile: str | None = None,
    external_userid: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return ListTransactionsQuery("wechat")(
        _transaction_filters(payment_status, product_code, mobile, external_userid, date_from, date_to),
        limit=limit,
        offset=offset,
    )


@router.get("/api/admin/wechat-pay/transactions/{order_no}")
def get_wechat_transaction(order_no: str) -> dict:
    try:
        return GetTransactionQuery("wechat")(order_no)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/alipay/transactions")
def list_alipay_transactions(
    payment_status: str | None = None,
    product_code: str | None = None,
    mobile: str | None = None,
    external_userid: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return ListTransactionsQuery("alipay")(
        _transaction_filters(payment_status, product_code, mobile, external_userid, date_from, date_to),
        limit=limit,
        offset=offset,
    )


@router.get("/api/admin/alipay/transactions/{order_no}")
def get_alipay_transaction(order_no: str) -> dict:
    try:
        return GetTransactionQuery("alipay")(order_no)
    except Exception as exc:
        _raise_http(exc)
