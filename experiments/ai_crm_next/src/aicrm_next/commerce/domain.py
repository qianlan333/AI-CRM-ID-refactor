from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aicrm_next.shared.errors import ContractError


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_price_cents(value: int) -> int:
    if not isinstance(value, int) or value < 0:
        raise ContractError("price_cents must be a non-negative integer")
    return value


def validate_quantity(value: int) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ContractError("quantity must be a positive integer")
    return value


def normalize_status(status: str | None) -> str:
    value = (status or "pending").strip().lower()
    if value not in {"pending", "paid", "failed", "closed"}:
        raise ContractError("unsupported payment_status")
    return value


def preview_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_code": product["product_code"],
        "title": product["title"],
        "description": product.get("description", ""),
        "price_cents": product["price_cents"],
        "currency": product.get("currency", "CNY"),
        "enabled": product.get("enabled", True),
        "cover_image": product.get("cover_image") or {"id": product.get("cover_image_id"), "data_url": ""},
        "detail_images": product.get("detail_images", []),
        "buy_button_text": product.get("buy_button_text", "立即购买"),
    }
