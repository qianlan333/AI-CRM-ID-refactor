from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import re
import secrets
from typing import Any

from aicrm_next.shared.runtime import database_mode, raw_database_url

from .product_code_aliases import canonical_product_code, canonical_product_name
from .wechat_shop_client import WeChatShopClient, WeChatShopClientConfig, WeChatShopClientError
from .wechat_shop_signature import callback_token, should_skip_signature_without_token, verify_signature

PROVIDER = "wechat_shop"
PROVIDER_LABEL = "微信小店"
TOKEN_REUSE_WINDOW = timedelta(minutes=10)
TOKEN_INVALID_CODES = {40001, 40014, 42001, 45009}

_FIXTURE_EVENTS: list[dict[str, Any]] = []
_FIXTURE_ORDERS: dict[str, dict[str, Any]] = {}
_FIXTURE_REFUNDS: list[dict[str, Any]] = []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _now_text() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _ts(value: Any) -> datetime | None:
    ts = _int(value)
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return _text(value)


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(raw_database_url(), row_factory=dict_row)


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(value if isinstance(value, (dict, list)) else {})


def _sanitize_error(value: Any) -> str:
    text = _text(value)
    text = re.sub(r"(access_token=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
    for secret in (os.getenv("WECHAT_SHOP_APPSECRET"), os.getenv("WECHAT_SHOP_CALLBACK_TOKEN")):
        if secret:
            text = text.replace(secret, "***")
    return text[:1000]


def sanitize_wechat_shop_error(value: Any) -> str:
    return _sanitize_error(value)


def _client() -> WeChatShopClient:
    timeout = _int(os.getenv("WECHAT_SHOP_HTTP_TIMEOUT_SECONDS"), 5) or 5
    return WeChatShopClient(
        WeChatShopClientConfig(
            appid=_text(os.getenv("WECHAT_SHOP_APPID")),
            appsecret=_text(os.getenv("WECHAT_SHOP_APPSECRET")),
            api_base=_text(os.getenv("WECHAT_SHOP_API_BASE")) or "https://api.weixin.qq.com",
            timeout_seconds=timeout,
        )
    )


def reset_wechat_shop_fixture_state() -> None:
    _FIXTURE_EVENTS.clear()
    _FIXTURE_ORDERS.clear()
    _FIXTURE_REFUNDS.clear()


def _extract_order_id(payload: dict[str, Any]) -> str:
    order_info = payload.get("order_info")
    if not isinstance(order_info, dict):
        return ""
    return _text(order_info.get("order_id"))


def _event_type(payload: dict[str, Any]) -> str:
    return _text(payload.get("Event") or payload.get("event") or payload.get("event_type"))


def _verify_query_signature(query_params: dict[str, Any] | None) -> None:
    token = callback_token()
    if not token:
        should_skip_signature_without_token()
        return
    params = dict(query_params or {})
    signature = _text(params.get("signature"))
    timestamp = _text(params.get("timestamp"))
    nonce = _text(params.get("nonce"))
    if not verify_signature(token, timestamp, nonce, signature):
        raise ValueError("invalid wechat shop callback signature")


def verify_echo(query_params: dict[str, Any]) -> str:
    _verify_query_signature(query_params)
    return _text(query_params.get("echostr")) or "ok"


def handle_wechat_shop_notify(payload: dict[str, Any], query_params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid wechat shop notify payload")
    _verify_query_signature(query_params)
    order_id = _extract_order_id(payload)
    if not order_id:
        raise ValueError("wechat shop order_id is required")
    event_id = _insert_event(payload, order_id=order_id)
    try:
        sync_result = sync_wechat_shop_order(order_id, source_event_id=event_id)
        _mark_event(event_id, "synced", "")
    except Exception as exc:
        error = _sanitize_error(exc)
        _mark_event(event_id, "failed", error)
        _record_order_error(order_id, error)
        sync_result = {"ok": False, "error_message": error}
    return {
        "ok": True,
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "order_id": order_id,
        "event_id": event_id,
        "sync_result": sync_result,
        "route_owner": "ai_crm_next",
        "source_status": "next_wechat_shop_notify",
        "fallback_used": False,
    }


def sync_wechat_shop_order(order_id: str, *, source_event_id: int | None = None, force_refresh_token: bool = False) -> dict[str, Any]:
    normalized_order_id = _text(order_id)
    if not normalized_order_id:
        raise ValueError("order_id is required")
    token = _get_access_token(force_refresh=force_refresh_token)
    try:
        raw = _client().get_order(normalized_order_id, token)
    except WeChatShopClientError as exc:
        code = _int(exc.payload.get("errcode"), -1)
        if code in TOKEN_INVALID_CODES and not force_refresh_token:
            token = _get_access_token(force_refresh=True)
            raw = _client().get_order(normalized_order_id, token)
        else:
            raise
    order_payload = _extract_order(raw)
    normalized = normalize_wechat_shop_order(order_payload, raw_response=raw, order_id=normalized_order_id)
    saved = _upsert_order(normalized, source_event_id=source_event_id)
    return {
        "ok": True,
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "order": saved,
        "source_status": "next_wechat_shop_order_sync",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
    }


def _extract_order(raw: dict[str, Any]) -> dict[str, Any]:
    order = raw.get("order")
    if isinstance(order, dict):
        return order
    order = raw.get("order_detail")
    if isinstance(order, dict):
        return {"order_detail": order, **{k: v for k, v in raw.items() if k != "order_detail"}}
    return raw


def _product_summary(product_infos: list[Any]) -> tuple[str, str, int, int]:
    names: list[str] = []
    codes: list[str] = []
    count = 0
    finished = 0
    for item in product_infos:
        if not isinstance(item, dict):
            continue
        sku_cnt = _int(item.get("sku_cnt") or item.get("product_count") or item.get("count"), 1) or 1
        count += sku_cnt
        finished += _int(item.get("finish_aftersale_sku_cnt") or item.get("finish_aftersale_sku_count"))
        title = _text(item.get("title") or item.get("product_name") or item.get("sku_title"))
        sku_code = _text(item.get("sku_id") or item.get("product_id") or item.get("sku_code") or item.get("product_code"))
        if title:
            names.append(title)
        if sku_code:
            codes.append(sku_code)
    return "、".join(names[:3]), ",".join(codes[:3]), count, finished


def _aftersale_counts(aftersale_detail: dict[str, Any], product_infos: list[Any]) -> tuple[int, int, int]:
    orders = aftersale_detail.get("aftersale_order_list") if isinstance(aftersale_detail, dict) else []
    if not isinstance(orders, list):
        orders = []
    total = len(orders)
    processing = 0
    finished = 0
    for item in orders:
        if not isinstance(item, dict):
            continue
        status = _int(item.get("status") or item.get("aftersale_status"))
        status_text = _text(item.get("status_desc") or item.get("aftersale_status_desc")).lower()
        if status in {20, 30, 40, 50, 100, 200} or "完成" in status_text or "finish" in status_text or "success" in status_text:
            finished += 1
        else:
            processing += 1
    product_finished = sum(_int(item.get("finish_aftersale_sku_cnt") or item.get("finish_aftersale_sku_count")) for item in product_infos if isinstance(item, dict))
    return total, processing, max(finished, product_finished)


def _is_virtual_delivery(delivery_info: dict[str, Any], order_detail: dict[str, Any]) -> bool:
    if _int(delivery_info.get("deliver_method")) in {1, 3}:
        return True
    delivery_product_info = order_detail.get("delivery_product_info")
    if isinstance(delivery_product_info, list):
        return any(isinstance(item, dict) and _int(item.get("deliver_type")) == 3 for item in delivery_product_info)
    if isinstance(delivery_product_info, dict):
        return _int(delivery_product_info.get("deliver_type")) == 3
    return False


def _buyer_mobile(delivery_info: dict[str, Any]) -> str:
    address_info = delivery_info.get("address_info") if isinstance(delivery_info.get("address_info"), dict) else {}
    return _text(
        address_info.get("virtual_order_tel_number")
        or address_info.get("purchaser_tel_number")
        or address_info.get("tel_number")
    )


def normalize_wechat_shop_order(order: dict[str, Any], *, raw_response: dict[str, Any] | None = None, order_id: str = "") -> dict[str, Any]:
    order_detail = order.get("order_detail") if isinstance(order.get("order_detail"), dict) else {}
    pay_info = order_detail.get("pay_info") if isinstance(order_detail.get("pay_info"), dict) else {}
    price_info = order_detail.get("price_info") if isinstance(order_detail.get("price_info"), dict) else {}
    delivery_info = order_detail.get("delivery_info") if isinstance(order_detail.get("delivery_info"), dict) else {}
    refund_info = order_detail.get("refund_info") if isinstance(order_detail.get("refund_info"), dict) else {}
    recharge_info = delivery_info.get("recharge_info") if isinstance(delivery_info.get("recharge_info"), dict) else {}
    product_infos = order_detail.get("product_infos") or order.get("product_infos") or []
    if not isinstance(product_infos, list):
        product_infos = []
    aftersale_detail = order.get("aftersale_detail") if isinstance(order.get("aftersale_detail"), dict) else {}
    status_code = _int(order.get("status"))
    pay_time = _int(pay_info.get("pay_time"))
    paid_at = _ts(pay_time)
    order_created_at = _ts(order.get("create_time") or order.get("create_time_s") or order_detail.get("create_time"))
    product_name, product_code, product_count, finish_sku_count = _product_summary(product_infos)
    canonical_code = canonical_product_code(product_code or product_name)
    canonical_name = canonical_product_name(canonical_code, product_name)
    aftersale_order_count, on_aftersale_order_count, finish_aftersale_count = _aftersale_counts(aftersale_detail, product_infos)
    finish_sku_count = max(finish_sku_count, finish_aftersale_count)
    deal_recorded = bool(pay_time > 0 or status_code in {20, 21, 30, 100})
    returned_recorded = bool(status_code == 200 or finish_sku_count > 0)
    business_status = "returned" if returned_recorded else "deal" if deal_recorded else "closed" if status_code == 250 else "pending"
    amount_total = _int(price_info.get("order_price") or price_info.get("order_price_cent"))
    refunded_amount_total = _int(refund_info.get("refund_freight"))
    returned_at = _ts(order.get("update_time")) if returned_recorded else None
    return {
        "order_id": _text(order_id or order.get("order_id")),
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "deal_recorded": deal_recorded,
        "returned_recorded": returned_recorded,
        "business_status": business_status,
        "status_code": status_code,
        "status_label": _text(order.get("status_desc") or order.get("status_label")),
        "created_at": order_created_at,
        "paid_at": paid_at,
        "returned_at": returned_at,
        "amount_total": amount_total,
        "refunded_amount_total": refunded_amount_total,
        "currency": "CNY",
        "transaction_id": _text(pay_info.get("transaction_id")),
        "payment_method": _int(pay_info.get("pay_method")) if pay_info.get("pay_method") is not None else None,
        "buyer_mobile": _buyer_mobile(delivery_info),
        "openid": _text(order.get("openid") or order_detail.get("openid") or pay_info.get("openid")),
        "unionid": _text(order.get("unionid") or order_detail.get("unionid") or pay_info.get("unionid")),
        "product_name": canonical_name or product_name or _text(order.get("product_name")) or "微信小店商品",
        "product_code": canonical_code or product_code,
        "product_count": product_count,
        "deliver_method": _int(delivery_info.get("deliver_method")) if delivery_info.get("deliver_method") is not None else None,
        "is_virtual_delivery": _is_virtual_delivery(delivery_info, order_detail),
        "virtual_account_no": _text(recharge_info.get("account_no")),
        "virtual_account_type": _text(recharge_info.get("account_type")),
        "aftersale_order_count": aftersale_order_count,
        "on_aftersale_order_count": on_aftersale_order_count,
        "finish_aftersale_sku_count": finish_sku_count,
        "raw_order_json": raw_response or order,
        "synced_at": _now(),
        "sync_status": "synced",
        "last_error": "",
    }


def _get_access_token(*, force_refresh: bool = False) -> str:
    appid = _text(os.getenv("WECHAT_SHOP_APPID"))
    if database_mode() == "postgres" and appid and not force_refresh:
        cached = _load_cached_token(appid)
        if cached:
            return cached
    payload = _client().get_stable_access_token(force_refresh=force_refresh)
    token = _text(payload.get("access_token"))
    if not token:
        raise WeChatShopClientError("wechat_shop stable_token response missing access_token", payload=payload)
    expires_in = max(60, _int(payload.get("expires_in"), 7200))
    if database_mode() == "postgres" and appid:
        _save_token(appid, token, expires_in)
    return token


def _load_cached_token(appid: str) -> str:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT access_token
            FROM wechat_shop_tokens
            WHERE appid = %s
              AND COALESCE(access_token, '') <> ''
              AND expires_at > %s
            LIMIT 1
            """,
            (appid, _now() + TOKEN_REUSE_WINDOW),
        ).fetchone()
    return _text((row or {}).get("access_token"))


def _save_token(appid: str, token: str, expires_in: int) -> None:
    expires_at = _now() + timedelta(seconds=expires_in)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO wechat_shop_tokens (appid, access_token, expires_at, refreshed_at, last_error, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, '', CURRENT_TIMESTAMP)
            ON CONFLICT (appid) DO UPDATE
            SET access_token = EXCLUDED.access_token,
                expires_at = EXCLUDED.expires_at,
                refreshed_at = CURRENT_TIMESTAMP,
                last_error = '',
                updated_at = CURRENT_TIMESTAMP
            """,
            (appid, token, expires_at),
        )


def _insert_event(payload: dict[str, Any], *, order_id: str) -> int:
    if database_mode() != "postgres":
        event = {
            "id": len(_FIXTURE_EVENTS) + 1,
            "event_type": _event_type(payload),
            "order_id": _text(order_id),
            "wechat_create_time": _int(payload.get("CreateTime")) or None,
            "from_user_name": _text(payload.get("FromUserName")),
            "to_user_name": _text(payload.get("ToUserName")),
            "raw_payload_json": deepcopy(payload),
            "process_status": "received",
            "error_message": "",
            "created_at": _now_text(),
            "updated_at": _now_text(),
        }
        _FIXTURE_EVENTS.append(event)
        return int(event["id"])
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO wechat_shop_order_events (
                event_type, order_id, wechat_create_time, from_user_name, to_user_name, raw_payload_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (event_type, order_id, wechat_create_time) DO UPDATE
            SET raw_payload_json = EXCLUDED.raw_payload_json,
                process_status = 'received',
                error_message = '',
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                _event_type(payload),
                _text(order_id),
                _int(payload.get("CreateTime")) or None,
                _text(payload.get("FromUserName")),
                _text(payload.get("ToUserName")),
                _jsonb(payload),
            ),
        ).fetchone()
    return int((row or {}).get("id") or 0)


def _mark_event(event_id: int | None, status: str, error: str) -> None:
    if not event_id:
        return
    if database_mode() != "postgres":
        for event in _FIXTURE_EVENTS:
            if int(event.get("id") or 0) == int(event_id):
                event["process_status"] = status
                event["error_message"] = error
                event["updated_at"] = _now_text()
        return
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wechat_shop_order_events
            SET process_status = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, error, int(event_id)),
        )


def _record_order_error(order_id: str, error: str) -> None:
    if database_mode() != "postgres":
        order = _FIXTURE_ORDERS.setdefault(
            _text(order_id),
            {
                "order_id": _text(order_id),
                "provider": PROVIDER,
                "provider_label": PROVIDER_LABEL,
                "business_status": "pending",
                "sync_status": "failed",
                "created_at": _now_text(),
            },
        )
        order["last_error"] = error
        order["sync_status"] = "failed"
        order["updated_at"] = _now_text()
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO wechat_shop_orders (order_id, last_error, sync_status, updated_at)
            VALUES (%s, %s, 'failed', CURRENT_TIMESTAMP)
            ON CONFLICT (order_id) DO UPDATE
            SET last_error = EXCLUDED.last_error,
                sync_status = 'failed',
                updated_at = CURRENT_TIMESTAMP
            """,
            (_text(order_id), error),
        )


def _upsert_order(order: dict[str, Any], *, source_event_id: int | None = None) -> dict[str, Any]:
    order = dict(order)
    order_id = _text(order.get("order_id"))
    if database_mode() != "postgres":
        existing = dict(_FIXTURE_ORDERS.get(order_id) or {})
        saved = {
            **existing,
            **order,
            "id": existing.get("id") or len(_FIXTURE_ORDERS) + 1,
            "last_event_type": _text(_FIXTURE_EVENTS[-1].get("event_type")) if _FIXTURE_EVENTS else existing.get("last_event_type", ""),
            "last_event_at": _now_text() if source_event_id else existing.get("last_event_at", ""),
            "created_at": _iso(order.get("created_at")) or existing.get("created_at") or _now_text(),
            "updated_at": _now_text(),
            "synced_at": _iso(order.get("synced_at")) or _now_text(),
            "paid_at": _iso(order.get("paid_at")),
            "returned_at": _iso(order.get("returned_at")),
        }
        _FIXTURE_ORDERS[order_id] = saved
        return deepcopy(saved)
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO wechat_shop_orders (
                order_id, provider, provider_label, deal_recorded, returned_recorded, business_status,
                status_code, status_label, paid_at, returned_at, amount_total, refunded_amount_total,
                currency, transaction_id, payment_method, buyer_mobile, openid, unionid, product_name, product_code,
                product_count, deliver_method, is_virtual_delivery, virtual_account_no, virtual_account_type,
                aftersale_order_count, on_aftersale_order_count, finish_aftersale_sku_count, raw_order_json,
                last_event_type, last_event_at, synced_at, sync_status, last_error, created_at, updated_at
            )
            VALUES (
                %(order_id)s, %(provider)s, %(provider_label)s, %(deal_recorded)s, %(returned_recorded)s,
                %(business_status)s, %(status_code)s, %(status_label)s, %(paid_at)s, %(returned_at)s,
                %(amount_total)s, %(refunded_amount_total)s, %(currency)s, %(transaction_id)s,
                %(payment_method)s, %(buyer_mobile)s, %(openid)s, %(unionid)s, %(product_name)s, %(product_code)s,
                %(product_count)s, %(deliver_method)s, %(is_virtual_delivery)s, %(virtual_account_no)s,
                %(virtual_account_type)s, %(aftersale_order_count)s, %(on_aftersale_order_count)s,
                %(finish_aftersale_sku_count)s, %(raw_order_json)s, %(last_event_type)s, %(last_event_at)s,
                %(synced_at)s, %(sync_status)s, %(last_error)s, COALESCE(%(created_at)s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP
            )
            ON CONFLICT (order_id) DO UPDATE
            SET provider = EXCLUDED.provider,
                provider_label = EXCLUDED.provider_label,
                deal_recorded = EXCLUDED.deal_recorded,
                returned_recorded = EXCLUDED.returned_recorded,
                business_status = EXCLUDED.business_status,
                status_code = EXCLUDED.status_code,
                status_label = EXCLUDED.status_label,
                paid_at = EXCLUDED.paid_at,
                returned_at = EXCLUDED.returned_at,
                amount_total = EXCLUDED.amount_total,
                refunded_amount_total = EXCLUDED.refunded_amount_total,
                currency = EXCLUDED.currency,
                transaction_id = EXCLUDED.transaction_id,
                payment_method = EXCLUDED.payment_method,
                buyer_mobile = EXCLUDED.buyer_mobile,
                openid = EXCLUDED.openid,
                unionid = EXCLUDED.unionid,
                product_name = EXCLUDED.product_name,
                product_code = EXCLUDED.product_code,
                product_count = EXCLUDED.product_count,
                deliver_method = EXCLUDED.deliver_method,
                is_virtual_delivery = EXCLUDED.is_virtual_delivery,
                virtual_account_no = EXCLUDED.virtual_account_no,
                virtual_account_type = EXCLUDED.virtual_account_type,
                aftersale_order_count = EXCLUDED.aftersale_order_count,
                on_aftersale_order_count = EXCLUDED.on_aftersale_order_count,
                finish_aftersale_sku_count = EXCLUDED.finish_aftersale_sku_count,
                raw_order_json = EXCLUDED.raw_order_json,
                last_event_type = EXCLUDED.last_event_type,
                last_event_at = EXCLUDED.last_event_at,
                synced_at = EXCLUDED.synced_at,
                sync_status = EXCLUDED.sync_status,
                last_error = '',
                created_at = EXCLUDED.created_at,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            {
                **order,
                "raw_order_json": _jsonb(order.get("raw_order_json") or {}),
                "last_event_type": _latest_event_type(source_event_id),
                "last_event_at": _now() if source_event_id else None,
            },
        ).fetchone()
    return dict(row or {})


def _latest_event_type(source_event_id: int | None) -> str:
    if not source_event_id:
        return ""
    if database_mode() != "postgres":
        for event in _FIXTURE_EVENTS:
            if int(event.get("id") or 0) == int(source_event_id):
                return _text(event.get("event_type"))
        return ""
    with _connect() as conn:
        row = conn.execute("SELECT event_type FROM wechat_shop_order_events WHERE id = %s", (int(source_event_id),)).fetchone()
    return _text((row or {}).get("event_type"))


def list_wechat_shop_events(filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(_int(limit, 50), 100))
    offset = max(0, _int(offset))
    order_id = _text((filters or {}).get("order_id"))
    if database_mode() != "postgres":
        rows = [deepcopy(event) for event in _FIXTURE_EVENTS]
        if order_id:
            rows = [event for event in rows if event.get("order_id") == order_id]
        rows.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
        return {
            "ok": True,
            "events": rows[offset : offset + limit],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "provider": PROVIDER,
            "provider_label": PROVIDER_LABEL,
            "route_owner": "ai_crm_next",
            "source_status": "next_wechat_shop_events",
            "fallback_used": False,
        }
    params: list[Any] = []
    where = ["1 = 1"]
    if order_id:
        where.append("order_id = %s")
        params.append(order_id)
    clause = " AND ".join(where)
    with _connect() as conn:
        total = int((conn.execute(f"SELECT count(*) AS total FROM wechat_shop_order_events WHERE {clause}", tuple(params)).fetchone() or {}).get("total") or 0)
        rows = conn.execute(
            f"""
            SELECT id, event_type, order_id, wechat_create_time, from_user_name, to_user_name,
                   process_status, error_message, created_at, updated_at
            FROM wechat_shop_order_events
            WHERE {clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, limit, offset]),
        ).fetchall()
    return {
        "ok": True,
        "events": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "route_owner": "ai_crm_next",
        "source_status": "next_wechat_shop_events",
        "fallback_used": False,
    }


def fixture_wechat_shop_orders() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in _FIXTURE_ORDERS.values()]


def fixture_wechat_shop_order(identifier: str) -> dict[str, Any] | None:
    needle = _text(identifier)
    for order in _FIXTURE_ORDERS.values():
        if needle in {_text(order.get("order_id")), _text(order.get("transaction_id")), _text(order.get("id"))}:
            return deepcopy(order)
    return None


def fixture_wechat_shop_refunds() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in _FIXTURE_REFUNDS]


def _out_refund_no() -> str:
    return "WSR" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(4).upper()


def _normalized_bool(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _refund_status_label(status: str) -> str:
    return {
        "requested": "退款申请已提交",
        "PROCESSING": "退款处理中",
        "SUCCESS": "退款成功",
        "failed": "退款申请失败",
    }.get(_text(status), _text(status) or "退款申请已提交")


def _extract_first_product(raw_order_json: Any) -> dict[str, Any]:
    raw = raw_order_json if isinstance(raw_order_json, dict) else {}
    order = raw.get("order") if isinstance(raw.get("order"), dict) else raw
    order_detail = order.get("order_detail") if isinstance(order.get("order_detail"), dict) else {}
    product_infos = order_detail.get("product_infos") or order.get("product_infos") or []
    if isinstance(product_infos, list) and product_infos:
        first = product_infos[0]
        return dict(first) if isinstance(first, dict) else {}
    return {}


def _wechat_shop_refund_request_payload(order: dict[str, Any], *, out_refund_no: str, amount_total: int, reason: str) -> dict[str, Any]:
    product = _extract_first_product(order.get("raw_order_json"))
    sku_id = _text(product.get("sku_id") or product.get("sku_code") or product.get("product_code") or order.get("product_code"))
    product_id = _text(product.get("product_id") or product.get("spu_id") or product.get("product_code") or sku_id)
    count = _int(product.get("sku_cnt") or product.get("product_count") or product.get("count"), 1) or 1
    return {
        "request_id": out_refund_no,
        "order_id": _text(order.get("order_id")),
        "product_id": product_id,
        "sku_id": sku_id,
        "amount": int(amount_total),
        "reason": reason[:80],
        "desc": reason[:200],
        "count": count,
        "type": "REFUND",
    }


def _load_refundable_order(order_id: str) -> dict[str, Any] | None:
    normalized_order_id = _text(order_id)
    if database_mode() != "postgres":
        order = fixture_wechat_shop_order(normalized_order_id)
        if not order:
            return None
        active = sum(
            _int(item.get("refund_amount_total"))
            for item in _FIXTURE_REFUNDS
            if item.get("order_id") == normalized_order_id and item.get("status") not in {"failed", "closed", "CLOSED", "SUCCESS"}
        )
        order["active_refund_amount_total"] = active
        return order
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT o.*,
                   (
                       SELECT COALESCE(SUM(r.refund_amount_total), 0)
                       FROM wechat_shop_refunds r
                       WHERE r.order_id = o.order_id
                         AND r.status NOT IN ('failed', 'closed', 'CLOSED', 'SUCCESS')
                   ) AS active_refund_amount_total
            FROM wechat_shop_orders o
            WHERE o.order_id = %s OR o.transaction_id = %s
            LIMIT 1
            """,
            (normalized_order_id, normalized_order_id),
        ).fetchone()
    return dict(row) if row else None


def _validate_refund_request(order: dict[str, Any], payload: dict[str, Any]) -> int:
    if not order:
        raise ValueError("订单不存在")
    order_id = _text(order.get("order_id"))
    if _text(payload.get("order_no_confirmation") or payload.get("transaction_id_confirmation")) != order_id:
        raise ValueError("微信小店订单号二次确认不匹配")
    if not _normalized_bool(payload.get("checked")):
        raise ValueError("请先勾选已核对付款人、商品、金额和微信小店订单号")
    amount_total = _int(order.get("amount_total"))
    refunded = _int(order.get("refunded_amount_total"))
    active = _int(order.get("active_refund_amount_total"))
    refundable = max(0, amount_total - refunded - active)
    if refundable <= 0:
        raise ValueError("当前订单没有可退金额")
    if order.get("returned_recorded") is True or _text(order.get("business_status")).lower() == "returned":
        raise ValueError("当前订单已记录退货，不能重复申请退款")
    if not (order.get("deal_recorded") is True or _text(order.get("business_status")).lower() == "deal"):
        raise ValueError("只有已成交的微信小店订单可以申请退款")
    if not _text(payload.get("reason")):
        raise ValueError("请选择退款原因")
    return refundable


def _insert_refund_record(order: dict[str, Any], *, out_refund_no: str, amount_total: int, reason: str, operator: str, request_payload: dict[str, Any]) -> None:
    if database_mode() != "postgres":
        _FIXTURE_REFUNDS.append(
            {
                "id": len(_FIXTURE_REFUNDS) + 1,
                "order_id": _text(order.get("order_id")),
                "transaction_id": _text(order.get("transaction_id")),
                "out_refund_no": out_refund_no,
                "aftersale_id": "",
                "refund_amount_total": amount_total,
                "order_amount_total": _int(order.get("amount_total")),
                "currency": _text(order.get("currency")) or "CNY",
                "status": "requested",
                "reason": reason,
                "requested_by": operator,
                "operator": operator,
                "request_payload_json": deepcopy(request_payload),
                "response_payload_json": {},
                "error_message": "",
                "created_at": _now_text(),
                "updated_at": _now_text(),
            }
        )
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO wechat_shop_refunds (
                order_id, transaction_id, out_refund_no, refund_amount_total, order_amount_total,
                currency, status, reason, requested_by, operator, request_payload_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'requested', %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (
                _text(order.get("order_id")),
                _text(order.get("transaction_id")),
                out_refund_no,
                amount_total,
                _int(order.get("amount_total")),
                _text(order.get("currency")) or "CNY",
                reason,
                operator,
                operator,
                _jsonb(request_payload),
            ),
        )


def _update_refund_record(out_refund_no: str, *, status: str, response_payload: dict[str, Any] | None = None, error_message: str = "") -> None:
    aftersale_id = _text((response_payload or {}).get("aftersale_id") or (response_payload or {}).get("after_sale_order_id"))
    if database_mode() != "postgres":
        for item in _FIXTURE_REFUNDS:
            if item.get("out_refund_no") == out_refund_no:
                item["status"] = status
                item["aftersale_id"] = aftersale_id or item.get("aftersale_id", "")
                item["response_payload_json"] = deepcopy(response_payload or {})
                item["error_message"] = error_message
                item["updated_at"] = _now_text()
        return
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wechat_shop_refunds
            SET status = %s,
                aftersale_id = COALESCE(NULLIF(%s, ''), aftersale_id),
                response_payload_json = %s,
                error_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE out_refund_no = %s
            """,
            (status, aftersale_id, _jsonb(response_payload or {}), error_message, out_refund_no),
        )


def create_wechat_shop_refund_request(order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    order = _load_refundable_order(order_id)
    amount_total = _validate_refund_request(order or {}, payload)
    reason = _text(payload.get("reason"))
    operator = _text(payload.get("operator")) or "aicrm_next"
    out_refund_no = _out_refund_no()
    request_payload = _wechat_shop_refund_request_payload(order or {}, out_refund_no=out_refund_no, amount_total=amount_total, reason=reason)
    _insert_refund_record(order or {}, out_refund_no=out_refund_no, amount_total=amount_total, reason=reason, operator=operator, request_payload=request_payload)
    try:
        token = _get_access_token()
        response_payload = _client().gen_after_sale_order(request_payload, token)
    except WeChatShopClientError as exc:
        code = _int(exc.payload.get("errcode"), -1)
        if code in TOKEN_INVALID_CODES:
            try:
                token = _get_access_token(force_refresh=True)
                response_payload = _client().gen_after_sale_order(request_payload, token)
            except Exception as retry_exc:
                error = _sanitize_error(retry_exc)
                _update_refund_record(out_refund_no, status="failed", response_payload=getattr(retry_exc, "payload", {}) or {}, error_message=error)
                raise ValueError(f"微信小店退款申请失败：{error}") from retry_exc
        else:
            error = _sanitize_error(exc)
            _update_refund_record(out_refund_no, status="failed", response_payload=exc.payload, error_message=error)
            raise ValueError(f"微信小店退款申请失败：{error}") from exc
    except Exception as exc:
        error = _sanitize_error(exc)
        _update_refund_record(out_refund_no, status="failed", response_payload={}, error_message=error)
        raise ValueError(f"微信小店退款申请失败：{error}") from exc
    _update_refund_record(out_refund_no, status="PROCESSING", response_payload=response_payload, error_message="")
    try:
        sync_wechat_shop_order(_text((order or {}).get("order_id")), force_refresh_token=False)
    except Exception:
        pass
    try:
        from .admin_unified_orders import get_order

        updated_order = get_order(_text((order or {}).get("order_id")), provider="wechat_shop")["order"]
    except Exception:
        updated_order = _load_refundable_order(_text((order or {}).get("order_id"))) or order or {}
    updated_order = dict(updated_order or {})
    updated_order["active_refund_amount_total"] = _int(updated_order.get("active_refund_amount_total")) or amount_total
    updated_order["active_refund_amount_yuan"] = f"{_int(updated_order.get('active_refund_amount_total')) / 100:.2f}"
    updated_order["refundable_amount_total"] = max(0, _int(updated_order.get("amount_total")) - _int(updated_order.get("refunded_amount_total")) - _int(updated_order.get("active_refund_amount_total")))
    updated_order["refundable_amount_yuan"] = f"{_int(updated_order.get('refundable_amount_total')) / 100:.2f}"
    updated_order["can_refund"] = False
    updated_order["status"] = "refund_processing"
    updated_order["status_label"] = "退货中"
    return {
        "ok": True,
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "order": updated_order,
        "refund": {
            "status": "PROCESSING",
            "status_label": _refund_status_label("PROCESSING"),
            "out_refund_no": out_refund_no,
            "refund_id": _text(response_payload.get("aftersale_id") or response_payload.get("after_sale_order_id")),
            "aftersale_id": _text(response_payload.get("aftersale_id") or response_payload.get("after_sale_order_id")),
            "provider_refund_executed": True,
        },
    }
