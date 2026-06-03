from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from aicrm_next.shared.errors import ContractError


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def safe_completion_redirect_url(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized.startswith("/") and not normalized.startswith("//") and "\\" not in normalized and not any(
        char.isspace() for char in normalized
    ):
        return normalized
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return normalized


def completion_redirect_projection(enabled: Any, url: Any) -> dict[str, Any]:
    safe_url = safe_completion_redirect_url(url)
    configured = bool(enabled)
    is_enabled = configured and bool(safe_url)
    completion_action = (
        {"type": "redirect", "redirect_url": safe_url}
        if is_enabled
        else {"type": "default", "redirect_url": ""}
    )
    return {
        "completion_redirect_enabled": configured,
        "completion_redirect_url": safe_url,
        "completion_redirect": {"enabled": is_enabled, "url": safe_url if is_enabled else ""},
        "completion_action": completion_action,
    }


def validate_completion_redirect(enabled: Any, url: Any) -> dict[str, Any]:
    raw_url = str(url or "").strip()
    safe_url = safe_completion_redirect_url(raw_url)
    if bool(enabled) and raw_url and not safe_url:
        raise ContractError("completion_redirect_url must be an https URL or safe internal path")
    return {
        "completion_redirect_enabled": bool(enabled),
        "completion_redirect_url": safe_url,
    }


def preview_product(product: dict[str, Any]) -> dict[str, Any]:
    completion_redirect = completion_redirect_projection(
        product.get("completion_redirect_enabled"),
        product.get("completion_redirect_url"),
    )
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
        **completion_redirect,
    }
