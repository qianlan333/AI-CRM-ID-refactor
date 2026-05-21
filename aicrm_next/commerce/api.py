from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from aicrm_next.shared.errors import ContractError, NotFoundError

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


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


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
