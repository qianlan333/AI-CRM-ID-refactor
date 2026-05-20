from __future__ import annotations

from typing import Any

from aicrm_next.shared.errors import ContractError, NotFoundError

from .domain import preview_product, validate_quantity
from .dto import CheckoutRequest, PaymentNotifyRequest, ProductUpsertRequest
from .payment_adapters import build_fake_payment_adapter
from .repo import CommerceRepository, build_commerce_repository


class ListProductsQuery:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = self._repo.list_products(limit=limit, offset=offset)
        return {"ok": True, **payload}


class GetProductQuery:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, product_id: str) -> dict[str, Any]:
        product = self._repo.get_product(product_id)
        if not product:
            raise NotFoundError("product not found")
        return {"ok": True, "product": product}


class GetPublicProductQuery:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, page_slug: str) -> dict[str, Any]:
        product = self._repo.get_product_by_slug(page_slug)
        if not product or not product.get("enabled"):
            raise NotFoundError("product not found")
        return {"ok": True, "product": preview_product(product)}


class UpsertProductCommand:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, payload: ProductUpsertRequest, product_id: str | None = None) -> dict[str, Any]:
        product = self._repo.save_product(payload.model_dump(), product_id)
        return {"ok": True, "product": product}


class SetProductEnabledCommand:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, product_id: str, *, enabled: bool) -> dict[str, Any]:
        return {"ok": True, "product": self._repo.set_product_enabled(product_id, enabled)}


class DeleteProductCommand:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, product_id: str) -> dict[str, Any]:
        return self._repo.delete_product(product_id)


class CheckoutCommand:
    def __init__(self, provider: str, repo: CommerceRepository | None = None) -> None:
        self._provider = provider
        self._repo = repo or build_commerce_repository()
        self._adapter = build_fake_payment_adapter(provider)

    def __call__(self, payload: CheckoutRequest) -> dict[str, Any]:
        quantity = validate_quantity(payload.quantity)
        product = self._repo.get_product_by_code(payload.product_code)
        if not product:
            raise NotFoundError("product not found")
        if not product.get("enabled"):
            raise ContractError("disabled product cannot checkout")
        amount = int(product["price_cents"]) * quantity
        identity = payload.buyer_identity.model_dump()
        order = self._repo.create_order(
            {
                "payment_provider": self._provider,
                "product_code": product["product_code"],
                "product_title": product["title"],
                "buyer_mobile": identity.get("mobile") or "",
                "external_userid": identity.get("external_userid") or "",
                "openid": identity.get("openid") or "",
                "unionid": identity.get("unionid") or "",
                "amount_cents": amount,
                "currency": product.get("currency", "CNY"),
                "quantity": quantity,
            }
        )
        checkout = self._adapter.build_checkout(order_no=order["order_no"], amount_cents=amount, return_url=payload.return_url)
        return {
            "ok": True,
            "order_no": order["order_no"],
            "payment_provider": self._provider,
            "amount_cents": amount,
            "payment_status": order["payment_status"],
            **checkout,
        }


class GetOrderQuery:
    def __init__(self, repo: CommerceRepository | None = None) -> None:
        self._repo = repo or build_commerce_repository()

    def __call__(self, order_no: str) -> dict[str, Any]:
        order = self._repo.get_order(order_no)
        if not order:
            raise NotFoundError("order not found")
        return {"ok": True, "order": order, "payment_status": order["payment_status"]}


class NotifyPaymentCommand:
    def __init__(self, provider: str, repo: CommerceRepository | None = None) -> None:
        self._provider = provider
        self._repo = repo or build_commerce_repository()

    def __call__(self, payload: PaymentNotifyRequest) -> dict[str, Any]:
        order = self._repo.apply_notify(payload.order_no, self._provider, payload.payment_status, payload.transaction_id)
        return {
            "ok": True,
            "order_no": order["order_no"],
            "payment_provider": self._provider,
            "payment_status": order["payment_status"],
            "transaction_id": order.get("transaction_id") or "",
            "source_status": "fake_signature_not_verified",
            "event_stub": {"would_emit": "payment_status_changed", "external_side_effect": False},
        }


class ListTransactionsQuery:
    def __init__(self, provider: str, repo: CommerceRepository | None = None) -> None:
        self._provider = provider
        self._repo = repo or build_commerce_repository()

    def __call__(self, filters: dict[str, Any], *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = self._repo.list_transactions(self._provider, filters, limit=limit, offset=offset)
        return {"ok": True, "filters": filters, **payload}


class GetTransactionQuery:
    def __init__(self, provider: str, repo: CommerceRepository | None = None) -> None:
        self._provider = provider
        self._repo = repo or build_commerce_repository()

    def __call__(self, order_no: str) -> dict[str, Any]:
        order = self._repo.get_order(order_no)
        if not order or order["payment_provider"] != self._provider:
            raise NotFoundError("transaction not found")
        return {"ok": True, "transaction": order}
