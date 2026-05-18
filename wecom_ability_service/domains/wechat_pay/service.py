from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from flask import current_app

from ...db import get_db
from ...infra.json_utils import safe_json_loads
from ...infra.settings import get_setting
from . import repo
from .client import WeChatPayClient, WeChatPayClientConfig, WeChatPayClientError


logger = logging.getLogger(__name__)


class WeChatPayConfigError(ValueError):
    pass


class WeChatPayOrderError(ValueError):
    pass


class WeChatPayProductError(ValueError):
    pass


PRODUCT_STATUS_DRAFT = "draft"
PRODUCT_STATUS_ACTIVE = "active"
PRODUCT_STATUS_DISABLED = "disabled"
PRODUCT_STATUSES = {PRODUCT_STATUS_DRAFT, PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_DISABLED}
PRODUCT_SLICE_LIMIT = 10


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _setting(key: str, default: str = "") -> str:
    stored = get_setting(key)
    if stored is not None:
        return _normalized_text(stored)
    return _normalized_text(current_app.config.get(key, default))


def _setting_bool(key: str, default: bool = False) -> bool:
    value = _setting(key)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _setting_int(key: str, default: int) -> int:
    try:
        return int(_setting(key) or default)
    except (TypeError, ValueError):
        return int(default)


def _client_config() -> WeChatPayClientConfig:
    app_id = _setting("WECHAT_PAY_APP_ID") or _setting("WECHAT_MP_APP_ID")
    return WeChatPayClientConfig(
        app_id=app_id,
        mch_id=_setting("WECHAT_PAY_MCH_ID"),
        api_v3_key=_setting("WECHAT_PAY_API_V3_KEY"),
        private_key_path=_setting("WECHAT_PAY_PRIVATE_KEY_PATH"),
        merchant_serial_no=_setting("WECHAT_PAY_CERT_SERIAL_NO"),
        platform_public_key_path=_setting("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH"),
        platform_serial_no=_setting("WECHAT_PAY_PLATFORM_CERT_SERIAL_NO"),
        api_base=_setting("WECHAT_PAY_API_BASE", "https://api.mch.weixin.qq.com") or "https://api.mch.weixin.qq.com",
        timeout_seconds=_setting_int("WECHAT_PAY_TIMEOUT_SECONDS", 10),
    )


def _create_wechat_pay_client() -> WeChatPayClient:
    config = _client_config()
    return WeChatPayClient(config)


def _require_ready_for_order() -> WeChatPayClientConfig:
    if not _setting_bool("WECHAT_PAY_ENABLED", False):
        raise WeChatPayConfigError("wechat_pay_disabled")
    config = _client_config()
    missing = []
    for key, value in {
        "WECHAT_PAY_APP_ID/WECHAT_MP_APP_ID": config.app_id,
        "WECHAT_PAY_MCH_ID": config.mch_id,
        "WECHAT_PAY_PRIVATE_KEY_PATH": config.private_key_path,
        "WECHAT_PAY_CERT_SERIAL_NO": config.merchant_serial_no,
    }.items():
        if not _normalized_text(value):
            missing.append(key)
    if missing:
        raise WeChatPayConfigError("missing WeChat Pay config: " + ", ".join(missing))
    return config


def _product_catalog() -> dict[str, dict[str, Any]]:
    raw = _setting("WECHAT_PAY_PRODUCT_CATALOG_JSON")
    payload = safe_json_loads(raw, default={}) if raw else {}
    catalog: dict[str, dict[str, Any]] = {}
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("products"), list):
            items = payload.get("products") or []
        else:
            items = [
                {"product_code": key, **(value if isinstance(value, dict) else {})}
                for key, value in payload.items()
            ]
    else:
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = _normalized_text(item.get("product_code") or item.get("code") or item.get("id"))
        if not code:
            continue
        amount_total = item.get("amount_total", item.get("amount_fen", item.get("price_fen", 0)))
        try:
            amount = int(amount_total)
        except (TypeError, ValueError):
            amount = 0
        catalog[code] = {
            "product_code": code,
            "name": _normalized_text(item.get("name") or item.get("title") or item.get("description") or code),
            "description": _normalized_text(item.get("description") or item.get("name") or item.get("title") or code),
            "amount_total": amount,
            "currency": _normalized_text(item.get("currency")) or "CNY",
            "success_url": _normalized_text(item.get("success_url")),
            "enabled": str(item.get("enabled", "true")).lower() not in {"0", "false", "no", "off"},
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "require_mobile": str(item.get("require_mobile", item.get("require_phone", "false"))).lower()
            in {"1", "true", "yes", "y", "on"},
            "cta_text": _normalized_text(item.get("cta_text")) or "确认支付",
            "lead_program_id": None,
            "lead_channel_id": None,
            "lead_plan_configured": False,
        }
    return catalog


def _money_amount_total(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> int:
    raw_amount = payload.get("amount_total")
    if raw_amount is not None and _normalized_text(raw_amount) != "":
        try:
            return int(raw_amount)
        except (TypeError, ValueError):
            raise WeChatPayProductError("价格格式不合法")
    for key in ("price_yuan", "price", "amount_yuan"):
        raw_yuan = payload.get(key)
        if raw_yuan is None or _normalized_text(raw_yuan) == "":
            continue
        try:
            return int(round(float(raw_yuan) * 100))
        except (TypeError, ValueError):
            raise WeChatPayProductError("价格格式不合法")
    if existing:
        return int(existing.get("amount_total") or 0)
    raise WeChatPayProductError("价格不能为空")


def _normalize_product_status(value: Any, *, default: str = PRODUCT_STATUS_DRAFT) -> str:
    normalized = _normalized_text(value) or default
    if normalized == "paused":
        normalized = PRODUCT_STATUS_DISABLED
    if normalized not in PRODUCT_STATUSES:
        raise WeChatPayProductError("商品状态不合法")
    return normalized


def _enabled_for_status(status: str) -> bool:
    return _normalized_text(status) == PRODUCT_STATUS_ACTIVE


def _generate_product_code() -> str:
    return "prd_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(3)


def _image_data_url(slice_row: dict[str, Any]) -> str:
    source_url = _normalized_text(slice_row.get("source_url"))
    if source_url:
        return source_url
    data_base64 = _normalized_text(slice_row.get("data_base64"))
    if not data_base64:
        return ""
    mime_type = _normalized_text(slice_row.get("mime_type")) or "image/png"
    return f"data:{mime_type};base64,{data_base64}"


def _present_slice(slice_row: dict[str, Any], *, include_image_url: bool = True) -> dict[str, Any]:
    item = {
        "id": int(slice_row.get("id") or 0),
        "product_id": int(slice_row.get("product_id") or 0),
        "image_library_id": int(slice_row.get("image_library_id") or 0),
        "sort_order": int(slice_row.get("sort_order") or 0),
        "name": _normalized_text(slice_row.get("image_name"))
        or _normalized_text(slice_row.get("file_name"))
        or f"切片 {int(slice_row.get('sort_order') or 0)}",
        "file_name": _normalized_text(slice_row.get("file_name")),
        "mime_type": _normalized_text(slice_row.get("mime_type")) or "image/png",
        "file_size": int(slice_row.get("file_size") or 0),
        "enabled": bool(slice_row.get("enabled")),
    }
    if include_image_url:
        item["image_url"] = _image_data_url(slice_row)
    return item


def _lead_qr_from_channel(channel: dict[str, Any] | None) -> dict[str, Any]:
    channel = dict(channel or {})
    qr_url = _normalized_text(channel.get("qr_url"))
    if not qr_url:
        return {}
    return {
        "channel_id": int(channel.get("id") or 0),
        "channel_name": _normalized_text(channel.get("channel_name")),
        "qr_url": qr_url,
        "status": _normalized_text(channel.get("status")),
        "owner_staff_id": _normalized_text(channel.get("owner_staff_id")),
    }


def resolve_lead_channel(program_id: int | None) -> dict[str, Any] | None:
    normalized_program_id = int(program_id or 0)
    if normalized_program_id <= 0:
        return None
    from ..automation_conversion import repo as automation_repo

    channels = automation_repo.list_channels_by_program(normalized_program_id, include_inactive=True)
    preferred = next(
        (
            channel
            for channel in channels
            if _normalized_text(channel.get("qr_url"))
            and _normalized_text(channel.get("status")) in {"active", "configured"}
        ),
        None,
    )
    if preferred:
        return preferred
    fallback = next((channel for channel in channels if _normalized_text(channel.get("qr_url"))), None)
    if fallback:
        return fallback
    return automation_repo.get_default_channel(program_id=normalized_program_id, allow_legacy_fallback=True)


def _lead_qr_for_product(product: dict[str, Any]) -> dict[str, Any]:
    from ..automation_conversion import repo as automation_repo

    channel_id = int(product.get("lead_channel_id") or 0)
    channel = automation_repo.get_channel_by_id(channel_id) if channel_id > 0 else None
    if not channel:
        channel = resolve_lead_channel(int(product.get("lead_program_id") or 0))
    return _lead_qr_from_channel(channel)


def _present_db_product(product: dict[str, Any]) -> dict[str, Any]:
    metadata = product.get("metadata_json") if isinstance(product.get("metadata_json"), dict) else {}
    lead_qr = _lead_qr_for_product(product) if int(product.get("lead_program_id") or 0) > 0 else {}
    return {
        "id": int(product.get("id") or 0),
        "product_code": _normalized_text(product.get("product_code")),
        "name": _normalized_text(product.get("name")),
        "description": _normalized_text(product.get("name")),
        "amount_total": int(product.get("amount_total") or 0),
        "currency": _normalized_text(product.get("currency")) or "CNY",
        "success_url": "",
        "enabled": bool(product.get("enabled")) and _normalized_text(product.get("status")) == PRODUCT_STATUS_ACTIVE,
        "status": _normalized_text(product.get("status")) or PRODUCT_STATUS_DRAFT,
        "metadata": metadata,
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("cta_text")) or "立即报名",
        "lead_program_id": int(product.get("lead_program_id") or 0) or None,
        "lead_channel_id": int(product.get("lead_channel_id") or 0) or None,
        "lead_plan_configured": bool(lead_qr.get("qr_url")),
        "lead_qr": lead_qr,
        "updated_at": _normalized_text(product.get("updated_at")),
        "created_at": _normalized_text(product.get("created_at")),
    }


def list_products() -> list[dict[str, Any]]:
    db_products = [_present_db_product(product) for product in repo.list_active_db_products()]
    db_codes = {_normalized_text(product.get("product_code")) for product in db_products}
    catalog_products = [
        product
        for product in _product_catalog().values()
        if product.get("enabled") and _normalized_text(product.get("product_code")) not in db_codes
    ]
    return db_products + catalog_products


def get_product(product_code: str) -> dict[str, Any] | None:
    code = _normalized_text(product_code)
    db_product = repo.get_product_by_code(code)
    if db_product:
        product = _present_db_product(db_product)
        return product if product.get("enabled") else None
    product = _product_catalog().get(code)
    if not product or not product.get("enabled"):
        return None
    return dict(product)


def get_product_slices(product_id: int, *, include_image_url: bool = True) -> list[dict[str, Any]]:
    if int(product_id or 0) <= 0:
        return []
    return [
        _present_slice(row, include_image_url=include_image_url)
        for row in repo.list_product_slices(int(product_id), include_image_data=include_image_url)
    ]


def get_public_product_page_state(product_code: str) -> dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    return {
        "product": product,
        "slices": get_product_slices(int(product.get("id") or 0)),
        "checkout_url": f"/pay/{product['product_code']}",
    }


def _normalize_slices_payload(slices: Any) -> list[dict[str, int]]:
    if not isinstance(slices, list):
        return []
    normalized: list[dict[str, int]] = []
    seen: set[int] = set()
    for index, item in enumerate(slices[:PRODUCT_SLICE_LIMIT]):
        if isinstance(item, dict):
            image_id = int(item.get("image_library_id") or item.get("id") or 0)
            sort_order = int(item.get("sort_order") or index + 1)
        else:
            image_id = int(item or 0)
            sort_order = index + 1
        if image_id <= 0 or image_id in seen:
            continue
        seen.add(image_id)
        normalized.append({"image_library_id": image_id, "sort_order": sort_order})
    return normalized


def _normalize_product_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    name = _normalized_text(payload.get("name")) or _normalized_text(existing.get("name"))
    if not name:
        raise WeChatPayProductError("商品名称不能为空")
    amount_total = _money_amount_total(payload, existing=existing)
    if amount_total <= 0:
        raise WeChatPayProductError("价格必须大于 0")
    status = _normalize_product_status(payload.get("status") if "status" in payload else existing.get("status"))
    lead_program_id = int(payload.get("lead_program_id") or existing.get("lead_program_id") or 0) or None
    lead_channel_id = int(payload.get("lead_channel_id") or existing.get("lead_channel_id") or 0) or None
    if lead_program_id:
        channel = resolve_lead_channel(lead_program_id)
        if not _normalized_text((channel or {}).get("qr_url")):
            raise WeChatPayProductError("所选引流计划未配置二维码")
        lead_channel_id = int((channel or {}).get("id") or 0) or lead_channel_id
    else:
        lead_channel_id = None
    return {
        "name": name[:120],
        "amount_total": amount_total,
        "currency": _normalized_text(payload.get("currency") or existing.get("currency")) or "CNY",
        "status": status,
        "enabled": _enabled_for_status(status),
        "cta_text": (_normalized_text(payload.get("cta_text")) or _normalized_text(existing.get("cta_text")) or "立即报名")[:24],
        "require_mobile": _normalized_bool(payload.get("require_mobile")) if "require_mobile" in payload else bool(existing.get("require_mobile")),
        "lead_program_id": lead_program_id,
        "lead_channel_id": lead_channel_id,
        "metadata": existing.get("metadata_json") if isinstance(existing.get("metadata_json"), dict) else {},
    }


def _present_admin_product(product: dict[str, Any], *, include_slices: bool = False) -> dict[str, Any]:
    item = _present_db_product(product)
    item["price_yuan"] = f"{item['amount_total'] / 100:.2f}"
    item["slice_count"] = int(product.get("slice_count") or len(get_product_slices(item["id"], include_image_url=False)))
    item.pop("description", None)
    item.pop("success_url", None)
    item.pop("lead_qr", None)
    if include_slices:
        item["slices"] = get_product_slices(item["id"], include_image_url=False)
    return item


def list_admin_products() -> list[dict[str, Any]]:
    return [_present_admin_product(product) for product in repo.list_admin_products()]


def get_admin_product(product_id: int) -> dict[str, Any]:
    product = repo.get_product_by_id(int(product_id))
    if not product:
        raise WeChatPayProductError("商品不存在")
    return _present_admin_product(product, include_slices=True)


def _product_share_qr_data_url(product_url: str) -> str:
    from io import BytesIO

    import segno

    qr = segno.make(_normalized_text(product_url), error="m", micro=False)
    buffer = BytesIO()
    qr.save(buffer, kind="svg", scale=6, xmldecl=False, svgns=True, nl=False)
    svg = buffer.getvalue().decode("utf-8")
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def build_admin_product_share(product_id: int, *, product_url: str) -> dict[str, Any]:
    product = get_admin_product(int(product_id))
    url = _normalized_text(product_url)
    if not url:
        raise WeChatPayProductError("商品链接生成失败")
    return {
        "product_id": int(product["id"]),
        "product_code": product["product_code"],
        "product_name": product["name"],
        "url": url,
        "qr_data_url": _product_share_qr_data_url(url),
    }


def create_admin_product(payload: dict[str, Any], *, operator: str = "") -> dict[str, Any]:
    del operator
    normalized = _normalize_product_payload(payload)
    product = repo.insert_product({"product_code": _generate_product_code(), **normalized})
    repo.replace_product_slices(int(product["id"]), _normalize_slices_payload(payload.get("slices")))
    get_db().commit()
    return get_admin_product(int(product["id"]))


def update_admin_product(product_id: int, payload: dict[str, Any], *, operator: str = "") -> dict[str, Any]:
    del operator
    existing = repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    normalized = _normalize_product_payload(payload, existing=existing)
    product = repo.update_product(int(product_id), normalized)
    if "slices" in payload:
        repo.replace_product_slices(int(product_id), _normalize_slices_payload(payload.get("slices")))
    get_db().commit()
    return get_admin_product(int(product["id"]))


def set_admin_product_status(product_id: int, status: str, *, operator: str = "") -> dict[str, Any]:
    del operator
    existing = repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    normalized_status = _normalize_product_status(status)
    payload = _normalize_product_payload({"status": normalized_status}, existing=existing)
    product = repo.update_product(int(product_id), payload)
    get_db().commit()
    return _present_admin_product(product)


def copy_admin_product(product_id: int, *, operator: str = "") -> dict[str, Any]:
    del operator
    existing = repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    payload = _normalize_product_payload(
        {
            "name": f"{_normalized_text(existing.get('name'))} 副本",
            "amount_total": int(existing.get("amount_total") or 0),
            "status": PRODUCT_STATUS_DRAFT,
            "cta_text": existing.get("cta_text"),
            "require_mobile": bool(existing.get("require_mobile")),
            "lead_program_id": existing.get("lead_program_id"),
            "lead_channel_id": existing.get("lead_channel_id"),
        },
        existing=existing,
    )
    product = repo.insert_product({"product_code": _generate_product_code(), **payload})
    source_slices = [
        {"image_library_id": item["image_library_id"], "sort_order": item["sort_order"]}
        for item in repo.list_product_slices(int(product_id), enabled_only=False, include_image_data=False)
    ]
    repo.replace_product_slices(int(product["id"]), source_slices)
    get_db().commit()
    return get_admin_product(int(product["id"]))


def delete_admin_product(product_id: int, *, operator: str = "") -> None:
    del operator
    if not repo.get_product_by_id(int(product_id)):
        raise WeChatPayProductError("商品不存在")
    repo.delete_product(int(product_id))
    get_db().commit()


def add_admin_product_slice(product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not repo.get_product_by_id(int(product_id)):
        raise WeChatPayProductError("商品不存在")
    current_count = len(repo.list_product_slices(int(product_id), enabled_only=False, include_image_data=False))
    if current_count >= PRODUCT_SLICE_LIMIT:
        raise WeChatPayProductError("全景贴图最多 10 张")
    image_library_id = int(payload.get("image_library_id") or 0)
    if image_library_id <= 0:
        raise WeChatPayProductError("请选择图片切片")
    repo.add_product_slice(int(product_id), image_library_id, sort_order=payload.get("sort_order"))
    get_db().commit()
    return get_admin_product(int(product_id))


def reorder_admin_product_slices(product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not repo.get_product_by_id(int(product_id)):
        raise WeChatPayProductError("商品不存在")
    slice_ids = [int(item) for item in (payload.get("slice_ids") or payload.get("slices") or []) if int(item or 0) > 0]
    repo.reorder_product_slices(int(product_id), slice_ids)
    get_db().commit()
    return get_admin_product(int(product_id))


def delete_admin_product_slice(product_id: int, slice_id: int) -> dict[str, Any]:
    repo.delete_product_slice(int(product_id), int(slice_id))
    get_db().commit()
    return get_admin_product(int(product_id))


def list_lead_plan_options() -> list[dict[str, Any]]:
    from ..automation_conversion import program_repo

    options = [
        {
            "program_id": 0,
            "program_name": "不配置引流计划",
            "status": "",
            "channel_id": None,
            "channel_name": "",
            "qr_url": "",
            "selectable": True,
        }
    ]
    # The product editor only needs program rows and channel QR URLs. Avoid
    # program_service.list_automation_programs(), which also computes workflow
    # summaries and can fail when unrelated runtime summary tables lag behind.
    for program in program_repo.list_program_rows(include_archived=False):
        status = _normalized_text(program.get("status"))
        if status not in {"active", "draft", "paused"}:
            continue
        channel = resolve_lead_channel(int(program.get("id") or 0))
        qr = _lead_qr_from_channel(channel)
        options.append(
            {
                "program_id": int(program.get("id") or 0),
                "program_name": _normalized_text(program.get("program_name")) or _normalized_text(program.get("program_code")),
                "status": status,
                "channel_id": qr.get("channel_id"),
                "channel_name": qr.get("channel_name", ""),
                "qr_url": qr.get("qr_url", ""),
                "selectable": bool(qr.get("qr_url")),
            }
        )
    return options


def _generate_out_trade_no() -> str:
    # WeChat Pay out_trade_no max length is 32. Keep this compact and sortable.
    return "WXP" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(6).upper()


def _safe_success_url(value: str) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    if normalized.startswith(("https://", "http://", "/")) and not normalized.startswith("//"):
        return normalized
    return ""


def _expires_at_text(minutes: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _order_public_payload(order: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "out_trade_no": _normalized_text(order.get("out_trade_no")),
        "product_code": _normalized_text(order.get("product_code")),
        "product_name": _normalized_text(order.get("product_name")),
        "amount_total": int(order.get("amount_total") or 0),
        "currency": _normalized_text(order.get("currency")) or "CNY",
        "status": _normalized_text(order.get("status")),
        "trade_state": _normalized_text(order.get("trade_state")),
        "success_url": _safe_success_url(order.get("success_url")),
        "paid_at": _normalized_text(order.get("paid_at")),
        "created_at": _normalized_text(order.get("created_at")),
    }
    if _normalized_text(order.get("status")) == "paid" or _normalized_text(order.get("trade_state")) == "SUCCESS":
        product = repo.get_product_by_code(payload["product_code"])
        if product:
            lead_qr = _lead_qr_for_product(product)
            if lead_qr.get("qr_url"):
                payload["lead_qr"] = lead_qr
    return payload


def _existing_paid_order_for_product(product: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any] | None:
    order = repo.get_paid_order_for_product_identity(
        product_code=_normalized_text(product.get("product_code")),
        payer_openid=_normalized_text(identity.get("openid")),
        unionid=_normalized_text(identity.get("unionid")),
        external_userid=_normalized_text(identity.get("external_userid")),
    )
    return _order_public_payload(order) if order else None


def _normalize_order_mobile(*, product: dict[str, Any], mobile: str) -> str:
    text = _normalized_text(mobile)
    if not text:
        if product.get("require_mobile"):
            raise WeChatPayOrderError("mobile_required")
        return ""
    from ..identity import service as identity_service

    try:
        return identity_service.normalize_mobile(text)
    except ValueError as exc:
        raise WeChatPayOrderError(str(exc)) from exc


def _mobile_binding_audit(
    *,
    mobile: str,
    openid: str,
    unionid: str,
    external_userid: str,
) -> dict[str, Any]:
    if not mobile:
        return {}
    try:
        from ...application.identity_contact.commands import BindExternalContactIdentityCommand
        from ...application.identity_contact.dto import (
            BindExternalContactIdentityCommandDTO,
            ResolveExternalContactIdentityQueryDTO,
        )
        from ...application.identity_contact.queries import ResolveExternalContactIdentityQuery

        resolved = ResolveExternalContactIdentityQuery()(
            ResolveExternalContactIdentityQueryDTO(
                openid=openid,
                unionid=unionid,
                external_userid=external_userid,
            )
        ) or {}
        resolved_external_userid = _normalized_text(resolved.get("external_userid")) or _normalized_text(external_userid)
        owner_userid = (
            _normalized_text(resolved.get("follow_user_userid"))
            or _normalized_text(resolved.get("owner_userid"))
            or _normalized_text(resolved.get("last_owner_userid"))
            or _normalized_text(resolved.get("first_owner_userid"))
        )
        if not resolved_external_userid:
            return {"status": "skipped", "reason": "external_userid_unresolved", "mobile": mobile}
        binding = BindExternalContactIdentityCommand()(
            BindExternalContactIdentityCommandDTO(
                external_userid=resolved_external_userid,
                owner_userid=owner_userid,
                bind_by_userid=owner_userid or "wechat_pay_h5",
                mobile=mobile,
                force_rebind=False,
            )
        )
        return {
            "status": "bound",
            "mobile": mobile,
            "external_userid": resolved_external_userid,
            "owner_userid": owner_userid,
            "person_id": (binding or {}).get("person_id") if isinstance(binding, dict) else None,
        }
    except Exception as exc:  # Do not block payment if identity binding cannot be resolved.
        logger.warning("wechat pay mobile bind skipped mobile=%s reason=%s", mobile, exc)
        return {"status": "skipped", "reason": str(exc), "mobile": mobile}


def _transaction_amount_total(transaction: dict[str, Any]) -> int:
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    return int(amount.get("total") or amount.get("payer_total") or 0)


def _transaction_currency(transaction: dict[str, Any]) -> str:
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    return _normalized_text(amount.get("currency")) or "CNY"


def _transaction_payer_openid(transaction: dict[str, Any]) -> str:
    payer = transaction.get("payer") if isinstance(transaction.get("payer"), dict) else {}
    return _normalized_text(payer.get("openid"))


def _transaction_attach_payload(transaction: dict[str, Any]) -> dict[str, Any]:
    payload = safe_json_loads(_normalized_text(transaction.get("attach")), default={})
    return payload if isinstance(payload, dict) else {}


def _match_recovered_product(transaction: dict[str, Any]) -> dict[str, Any]:
    amount_total = _transaction_amount_total(transaction)
    description = _normalized_text(transaction.get("description"))
    attach = _transaction_attach_payload(transaction)
    product_code = _normalized_text(attach.get("product_code"))
    if product_code:
        product = get_product(product_code)
        if product:
            return product
    for product in list_products():
        if amount_total and int(product.get("amount_total") or 0) != amount_total:
            continue
        names = {
            _normalized_text(product.get("name")),
            _normalized_text(product.get("description")),
        }
        if description and description in names:
            return product
    return {
        "product_code": product_code or "recovered_wechat_pay",
        "name": description or "微信支付恢复订单",
        "description": description or "微信支付恢复订单",
        "amount_total": amount_total,
        "currency": _transaction_currency(transaction),
        "success_url": "",
        "metadata": {},
    }


def _recover_missing_order_from_transaction(transaction: dict[str, Any], *, event_type: str) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    if not out_trade_no:
        return {}
    existing = repo.get_order(out_trade_no)
    if existing:
        return existing
    amount_total = _transaction_amount_total(transaction)
    if amount_total <= 0:
        raise WeChatPayOrderError("order_not_found")
    attach = _transaction_attach_payload(transaction)
    product = _match_recovered_product(transaction)
    product_code = _normalized_text(product.get("product_code")) or "recovered_wechat_pay"
    product_name = _normalized_text(product.get("name") or product.get("description")) or product_code
    logger.warning(
        "recover missing WeChat Pay order out_trade_no=%s transaction_id=%s event_type=%s product_code=%s",
        out_trade_no,
        _normalized_text(transaction.get("transaction_id")),
        event_type,
        product_code,
    )
    return repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "order_source": f"recovered_{event_type}",
            "client_order_ref": _normalized_text(attach.get("client_order_ref")),
            "product_code": product_code,
            "product_name": product_name,
            "description": _normalized_text(transaction.get("description")) or product_name,
            "amount_total": amount_total,
            "currency": _transaction_currency(transaction),
            "payer_openid": _transaction_payer_openid(transaction),
            "status": "created",
            "success_url": _normalized_text(product.get("success_url")),
            "metadata": {
                "recovered": True,
                "recovered_event_type": event_type,
            },
            "request_meta": {
                "recovered_from_wechat_transaction": True,
                "transaction_id": _normalized_text(transaction.get("transaction_id")),
            },
        }
    )


def create_jsapi_order(
    *,
    product_code: str,
    payer_openid: str,
    respondent_key: str = "",
    unionid: str = "",
    external_userid: str = "",
    payer_name: str = "",
    client_order_ref: str = "",
    order_source: str = "h5_checkout",
    notify_url: str,
    mobile: str = "",
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _require_ready_for_order()
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    openid = _normalized_text(payer_openid)
    if not openid:
        raise WeChatPayOrderError("openid_required")
    amount_total = int(product.get("amount_total") or 0)
    if amount_total <= 0:
        raise WeChatPayOrderError("product_amount_invalid")
    existing_paid_order = _existing_paid_order_for_product(
        product,
        {"openid": openid, "unionid": unionid, "external_userid": external_userid},
    )
    if existing_paid_order:
        raise WeChatPayOrderError("already_paid")
    normalized_mobile = _normalize_order_mobile(product=product, mobile=mobile)
    request_meta_payload = dict(request_meta or {})
    identity_external_userid = _normalized_text(external_userid)
    userid_snapshot = ""
    if normalized_mobile:
        mobile_binding = _mobile_binding_audit(
            mobile=normalized_mobile,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
        request_meta_payload["mobile_binding"] = mobile_binding
        if isinstance(mobile_binding, dict) and mobile_binding.get("status") == "bound":
            identity_external_userid = _normalized_text(mobile_binding.get("external_userid")) or identity_external_userid
            userid_snapshot = _normalized_text(mobile_binding.get("owner_userid"))
    out_trade_no = _generate_out_trade_no()
    success_url = _safe_success_url(product.get("success_url"))
    order = repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "order_source": order_source,
            "client_order_ref": client_order_ref,
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["description"],
            "amount_total": amount_total,
            "currency": product.get("currency") or "CNY",
            "payer_openid": openid,
            "respondent_key": respondent_key,
            "unionid": unionid,
            "external_userid": identity_external_userid,
            "userid_snapshot": userid_snapshot,
            "mobile_snapshot": normalized_mobile,
            "payer_name_snapshot": _normalized_text(payer_name),
            "status": "created",
            "success_url": success_url,
            "metadata": product.get("metadata") or {},
            "request_meta": request_meta_payload,
            "expires_at": _expires_at_text(),
        }
    )
    transaction_payload = {
        "appid": config.app_id,
        "mchid": config.mch_id,
        "description": product["description"][:127],
        "out_trade_no": out_trade_no,
        "notify_url": _normalized_text(notify_url),
        "amount": {"total": amount_total, "currency": product.get("currency") or "CNY"},
        "payer": {"openid": openid},
        "attach": json.dumps(
            {"product_code": product["product_code"], "client_order_ref": client_order_ref},
            ensure_ascii=False,
            separators=(",", ":"),
        )[:128],
    }
    try:
        client = _create_wechat_pay_client()
        response_payload = client.create_jsapi_transaction(transaction_payload)
        prepay_id = _normalized_text(response_payload.get("prepay_id"))
        if not prepay_id:
            raise WeChatPayClientError("missing prepay_id from WeChat Pay")
        order = repo.update_order_payment_request(
            out_trade_no,
            prepay_id=prepay_id,
            request_payload=transaction_payload,
            response_payload=response_payload,
        )
        pay_params = client.build_jsapi_pay_params(prepay_id)
        get_db().commit()
    except Exception as exc:
        repo.mark_order_failed(out_trade_no, error_message=str(exc))
        get_db().commit()
        raise
    return {
        "order": _order_public_payload(order),
        "pay_params": pay_params,
    }


def _apply_transaction(transaction: dict[str, Any], *, event_type: str, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    if not out_trade_no:
        raise WeChatPayOrderError("out_trade_no_missing")
    order = repo.update_order_from_transaction(transaction)
    if not order:
        _recover_missing_order_from_transaction(transaction, event_type=event_type)
        order = repo.update_order_from_transaction(transaction)
    if not order:
        raise WeChatPayOrderError("order_not_found")
    repo.insert_event(
        out_trade_no=out_trade_no,
        event_type=event_type,
        transaction_id=_normalized_text(transaction.get("transaction_id")),
        trade_state=_normalized_text(transaction.get("trade_state")),
        payload=transaction,
        headers=headers or {},
    )
    get_db().commit()
    return order


def handle_wechat_pay_notification(*, body: str, headers: dict[str, Any]) -> dict[str, Any]:
    client = _create_wechat_pay_client()
    transaction = client.verify_and_decrypt_notification(body=body, headers=headers)
    order = _apply_transaction(transaction, event_type="notify", headers=headers)
    return {"order": _order_public_payload(order), "transaction": transaction}


def get_order_status(*, out_trade_no: str, refresh: bool = False) -> dict[str, Any]:
    order = repo.get_order(out_trade_no)
    if not order and refresh:
        client = _create_wechat_pay_client()
        transaction = client.query_order_by_out_trade_no(out_trade_no)
        order = _apply_transaction(transaction, event_type="query")
    if not order:
        raise WeChatPayOrderError("order_not_found")
    if refresh and _normalized_text(order.get("status")) not in {"paid", "closed"}:
        client = _create_wechat_pay_client()
        transaction = client.query_order_by_out_trade_no(out_trade_no)
        order = _apply_transaction(transaction, event_type="query")
    return {"order": _order_public_payload(order)}


def build_checkout_page_state(
    *,
    product_code: str,
    identity: dict[str, str] | None,
    oauth_start_url: str,
) -> dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    identity_payload = dict(identity or {})
    paid_order = _existing_paid_order_for_product(product, identity_payload) if identity_payload else None
    return {
        "product": product,
        "identity_ready": bool(_normalized_text(identity_payload.get("openid"))),
        "oauth_start_url": oauth_start_url,
        "create_order_url": "/api/h5/wechat-pay/jsapi/orders",
        "status_url_template": "/api/h5/wechat-pay/orders/{out_trade_no}",
        "enabled": _setting_bool("WECHAT_PAY_ENABLED", False),
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("cta_text")) or "确认支付",
        "lead_plan_configured": bool(product.get("lead_plan_configured")),
        "paid_order": paid_order,
    }
