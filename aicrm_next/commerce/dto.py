from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProductUpsertRequest(BaseModel):
    product_code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    price_cents: int = 0
    currency: str = "CNY"
    enabled: bool = True
    page_slug: str | None = None
    cover_image_id: str | None = None
    detail_image_ids: list[str] = Field(default_factory=list)
    detail_sections: list[dict[str, Any]] = Field(default_factory=list)
    buy_button_text: str = "立即购买"
    completion_redirect_enabled: bool = False
    completion_redirect_url: str = ""


class BuyerIdentity(BaseModel):
    mobile: str | None = None
    external_userid: str | None = None
    openid: str | None = None
    unionid: str | None = None


class CheckoutRequest(BaseModel):
    product_code: str
    buyer_identity: BuyerIdentity = Field(default_factory=BuyerIdentity)
    quantity: int = 1
    return_url: str | None = None


class PaymentNotifyRequest(BaseModel):
    order_no: str
    payment_status: Literal["paid", "failed", "pending"] = "paid"
    transaction_id: str | None = None
    provider_payload: dict[str, Any] = Field(default_factory=dict)
