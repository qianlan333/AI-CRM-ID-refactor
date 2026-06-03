from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.frontend_compat.admin_shell import shell_context
from aicrm_next.shared.errors import ContractError, NotFoundError

from .admin_transactions import (
    default_filters,
    create_wechat_refund_request,
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
_COMMERCE_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FRONTEND_COMPAT_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=[_COMMERCE_TEMPLATES_DIR, _FRONTEND_COMPAT_TEMPLATES_DIR])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _product_admin_context(
    request: Request,
    *,
    page_title: str,
    page_summary: str,
    mode: str,
    product: dict | None = None,
) -> dict:
    context = shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint="api.admin_wechat_pay_products_page",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "商品管理", "href": request.url_for("api.admin_wechat_pay_products_page")},
    ]
    if mode != "list":
        context["breadcrumbs"].append({"label": "创建商品" if mode == "new" else "编辑商品"})
    context.update(
        {
            "product_page_mode": mode,
            "initial_product": jsonable_encoder(product or {}),
            "initial_product_json": json.dumps(jsonable_encoder(product or {}), ensure_ascii=False),
        }
    )
    return context


def _share_payload(request: Request, product: dict) -> dict:
    product_code = str(product.get("product_code") or "")
    url = str(request.base_url).rstrip("/") + f"/p/{quote(product_code)}"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'>"
        "<rect width='256' height='256' fill='#ffffff'/>"
        "<rect x='24' y='24' width='208' height='208' fill='none' stroke='#111827' stroke-width='12'/>"
        "<text x='128' y='126' text-anchor='middle' font-size='20' font-family='monospace' fill='#111827'>"
        "PRODUCT"
        "</text>"
        "<text x='128' y='158' text-anchor='middle' font-size='14' font-family='monospace' fill='#475569'>"
        f"{product_code[:18]}"
        "</text>"
        "</svg>"
    )
    return {
        "product_id": str(product.get("id") or ""),
        "product_code": product_code,
        "product_name": str(product.get("title") or ""),
        "url": url,
        "qr_data_url": "data:image/svg+xml;utf8," + quote(svg),
    }


@router.get("/admin/wechat-pay/products", response_class=HTMLResponse, name="api.admin_wechat_pay_products_page")
def admin_wechat_pay_products_page(request: Request):
    try:
        payload = ListProductsQuery()(limit=100, offset=0)
    except Exception as exc:
        payload = {"ok": False, "items": [], "total": 0, "page_error": str(exc)}
    context = _product_admin_context(
        request,
        page_title="微信支付商品管理",
        page_summary="创建、编辑和上下架微信支付商品。",
        mode="list",
    )
    products = payload.get("items") or []
    context.update(
        {
            "initial_products": jsonable_encoder(products),
            "initial_products_json": json.dumps(jsonable_encoder(products), ensure_ascii=False),
            "product_total": int(payload.get("total") or len(products)),
            "page_error": str(payload.get("page_error") or ""),
        }
    )
    return templates.TemplateResponse(request, "wechat_products.html", context, status_code=200 if payload.get("ok", True) else 503)


@router.get("/admin/wechat-pay/products/new", response_class=HTMLResponse, name="api.admin_wechat_pay_product_new_page")
def admin_wechat_pay_product_new_page(request: Request):
    context = _product_admin_context(
        request,
        page_title="创建微信支付商品",
        page_summary="配置商品编码、名称、价格与上架状态。",
        mode="new",
    )
    return templates.TemplateResponse(request, "wechat_products.html", context)


@router.get("/admin/wechat-pay/products/{product_id}/edit", response_class=HTMLResponse, name="api.admin_wechat_pay_product_edit_page")
def admin_wechat_pay_product_edit_page(request: Request, product_id: str):
    try:
        product = GetProductQuery()(product_id)["product"]
    except Exception as exc:
        context = _product_admin_context(
            request,
            page_title="商品不存在",
            page_summary="当前没有找到这个商品。",
            mode="edit",
        )
        context["page_error"] = str(exc)
        return templates.TemplateResponse(request, "wechat_products.html", context, status_code=404)
    context = _product_admin_context(
        request,
        page_title=f"编辑商品 {product.get('product_code')}",
        page_summary="维护商品名称、价格与上架状态。",
        mode="edit",
        product=product,
    )
    return templates.TemplateResponse(request, "wechat_products.html", context)


@router.get("/admin/wechat-pay/transactions", response_class=HTMLResponse, name="api.admin_wechat_pay_transactions_page")
def admin_wechat_transactions_page(request: Request):
    context = shell_context(
        request=request,
        page_title="微信支付交易管理",
        page_summary="按订单创建时间检索微信支付订单、导出筛选结果，并进入详情页查看订单与退款状态。",
        active_endpoint="api.admin_wechat_pay_transactions_page",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "交易管理"},
    ]
    context.update(
        {
            "default_filters": default_filters(),
            "product_options": list_wechat_product_options(),
        }
    )
    return templates.TemplateResponse(
        request,
        "wechat_transactions.html",
        context,
    )


@router.get("/admin/wechat-pay/transactions/{order_id}", response_class=HTMLResponse, name="api.admin_wechat_pay_transaction_detail_page")
def admin_wechat_transaction_detail_page(request: Request, order_id: str) -> Response:
    order = get_wechat_admin_order(order_id)
    context = shell_context(
        request=request,
        page_title="微信支付订单详情",
        page_summary="核对订单状态、退款金额，并提交退款申请。",
        active_endpoint="api.admin_wechat_pay_transactions_page",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "交易管理", "href": request.url_for("api.admin_wechat_pay_transactions_page")},
        {"label": "订单详情"},
    ]
    context.update(
        {
            "detail_order": order,
            "detail_error": "" if order else "订单不存在",
            "default_filters": default_filters(),
            "product_options": list_wechat_product_options(),
        }
    )
    return templates.TemplateResponse(
        request,
        "wechat_transactions.html",
        context,
        status_code=200 if order else 404,
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


@router.post("/api/admin/wechat-pay/orders/{order_id}/refunds")
async def request_wechat_admin_refund(order_id: str, request: Request) -> JSONResponse:
    payload = await request.json()
    try:
        result = create_wechat_refund_request(order_id, payload if isinstance(payload, dict) else {})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse(result)


@router.get("/api/admin/wechat-pay/products")
def list_products(limit: int = 50, offset: int = 0) -> dict:
    try:
        return ListProductsQuery()(limit=limit, offset=offset)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/wechat-pay/products/{product_id}")
def get_product(product_id: str) -> dict:
    try:
        return GetProductQuery()(product_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/wechat-pay/products/{product_id}/share")
def share_product(product_id: str, request: Request) -> dict:
    try:
        product = GetProductQuery()(product_id)["product"]
    except Exception as exc:
        _raise_http(exc)
    return {"ok": True, "share": _share_payload(request, product)}


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
