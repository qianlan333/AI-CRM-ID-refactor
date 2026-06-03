from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from aicrm_next.shared.errors import ContractError

PRODUCT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,80}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_product_code(value: str) -> str:
    product_code = str(value or "").strip()
    if not PRODUCT_CODE_PATTERN.fullmatch(product_code):
        raise ContractError("product_code must be 3-80 characters of letters, numbers, underscore, or hyphen")
    return product_code


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
