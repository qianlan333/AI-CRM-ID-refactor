from __future__ import annotations

import json
import os
import secrets
import hashlib
import hmac
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_GENERIC_PUSH, WEBHOOK_ORDER_PAID_PUSH
from aicrm_next.platform_foundation.legacy_cleanup.service import LegacyWebhookCleanupService
from aicrm_next.shared.runtime import production_data_ready

from .external_push_outbox import DEFAULT_TENANT_ID, EVENT_TRANSACTION_PAID, resolve_product_for_order as _resolve_product_for_order
from .repo import connect_commerce_db


EVENT_EXTERNAL_PUSH_TEST = "external_push.test"
MAX_BODY_BYTES = 8192
QUESTIONNAIRE_TITLE_PAYMENT_OPEN_MEMBER = "微信支付开通黄小璨会员"
WEBHOOK_LOCAL_TIMEZONE = timezone(timedelta(hours=8))


class ExternalPushAdminError(ValueError):
    pass


class WebhookUrlValidationError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _record_legacy_marker(legacy_key: str, *, metadata: dict[str, Any] | None = None) -> None:
    try:
        LegacyWebhookCleanupService().record_runtime_marker(
            legacy_key,
            marker="legacy_path_invoked",
            operator="commerce.external_push_admin",
            metadata=metadata or {},
            real_external_call_executed=False,
        )
    except Exception:
        pass


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(_text(address).strip("[]"))
    except ValueError as exc:
        raise WebhookUrlValidationError("webhook_url DNS resolved to an invalid IP") from exc
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if str(ip) == "169.254.169.254":
        return True
    return False


def _validate_webhook_url(url: str) -> str:
    parsed = urlparse(_text(url))
    if parsed.scheme.lower() != "https":
        raise WebhookUrlValidationError("webhook_url must be an https URL")
    if not parsed.hostname:
        raise WebhookUrlValidationError("webhook_url host is required")
    hostname = parsed.hostname.strip().lower()
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or hostname.endswith(".localhost"):
        raise WebhookUrlValidationError("webhook_url host is not allowed")
    try:
        if _is_blocked_ip(hostname):
            raise WebhookUrlValidationError("webhook_url host must resolve to a public IP")
    except WebhookUrlValidationError as exc:
        if "invalid IP" not in str(exc):
            raise
    return parsed.geturl()


def _resolve_and_validate_public_https_url(url: str) -> str:
    normalized = _validate_webhook_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookUrlValidationError("webhook_url DNS resolution failed") from exc
    resolved_ips = {item[4][0] for item in addr_infos if item and item[4]}
    if not resolved_ips:
        raise WebhookUrlValidationError("webhook_url DNS resolution returned no IP")
    for address in resolved_ips:
        if _is_blocked_ip(address):
            raise WebhookUrlValidationError("webhook_url resolved to a non-public IP")
    return normalized


resolve_and_validate_public_https_url = _resolve_and_validate_public_https_url


def _iso(value: Any = None) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = _text(value)
        if text:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return text
        else:
            dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_local(value: Any = None) -> str:
    text = _iso(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return dt.astimezone(WEBHOOK_LOCAL_TIMEZONE).isoformat()


def _mask_openid(value: Any) -> str:
    text = _text(value)
    if len(text) <= 8:
        return text[:2] + "***" if text else ""
    return f"{text[:4]}***{text[-4:]}"


def _mask_phone(value: Any) -> str:
    digits = _text(value)
    if len(digits) < 7:
        return "***" if digits else ""
    return f"{digits[:3]}****{digits[-4:]}"


def _redact_sensitive_fields(payload: Any) -> Any:
    if isinstance(payload, list):
        return [_redact_sensitive_fields(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if lowered in {"secret", "webhook_secret", "pay_sign", "paysign", "api_v3_key", "private_key"}:
            redacted[key] = "[REDACTED]"
        elif lowered in {"phone", "mobile", "mobile_snapshot", "phone_number"}:
            redacted[key] = _mask_phone(value)
        elif lowered in {"openid", "payer_openid", "unionid"}:
            redacted[key] = _mask_openid(value)
        else:
            redacted[key] = _redact_sensitive_fields(value)
    return redacted


def _sign_webhook_payload(secret: str, timestamp: int | str, raw_body: str) -> str:
    digest = hmac.new(
        _text(secret).encode("utf-8"),
        f"{_text(timestamp)}.{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _truncate_body(body: Any, max_bytes: int = MAX_BODY_BYTES) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _build_external_push_payload(
    event: str,
    order: dict[str, Any],
    product: dict[str, Any],
    config: dict[str, Any],
    *,
    delivery_id: str,
) -> dict[str, Any]:
    event_type = _text(event)
    if event_type == EVENT_EXTERNAL_PUSH_TEST:
        return {
            "event": EVENT_EXTERNAL_PUSH_TEST,
            "delivery_id": delivery_id,
            "occurred_at": _iso(),
            "tenant": {"id": _text(config.get("tenant_id")) or DEFAULT_TENANT_ID},
            "product": {
                "id": str(product.get("id") or config.get("target_id") or ""),
                "name": _text(product.get("name")),
            },
            "custom_params": config.get("custom_params") if isinstance(config.get("custom_params"), dict) else {},
        }
    order_payload = {
        "id": str(order.get("id") or ""),
        "order_no": _text(order.get("out_trade_no")),
        "out_trade_no": _text(order.get("out_trade_no")),
        "status": "paid",
        "paid_amount": int(order.get("payer_total") or order.get("amount_total") or 0),
        "paid_at": _iso(order.get("paid_at")),
        "pay_channel": "wechat",
    }
    product_payload = {
        "id": str(product.get("id") or ""),
        "code": _text(product.get("product_code")),
        "name": _text(product.get("name") or order.get("product_name")),
        "price": int(product.get("amount_total") or order.get("amount_total") or 0),
    }
    return {
        "phone_number": _text(order.get("mobile_snapshot")),
        "type": _text(config.get("push_type")),
        "day": config.get("day"),
        "frequency": config.get("frequency"),
        "remark": _text(config.get("remark")),
        "submitted_at": _iso_local(order.get("paid_at")),
        "questionnaire_title": QUESTIONNAIRE_TITLE_PAYMENT_OPEN_MEMBER,
        "delivery_id": delivery_id,
        "event": EVENT_TRANSACTION_PAID,
        "order": order_payload,
        "product": product_payload,
        "buyer": {
            "id": _text(order.get("external_userid") or order.get("userid_snapshot") or order.get("respondent_key")),
            "openid": _mask_openid(order.get("payer_openid")),
            "unionid": _text(order.get("unionid")),
            "phone": _text(order.get("mobile_snapshot")),
        },
    }


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _connect():
    if not production_data_ready():
        raise ExternalPushAdminError("production_database_required")
    return connect_commerce_db()


def _public_delivery(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["config_id"] = int(payload.get("config_id") or 0)
    payload["order_id"] = int(payload.get("order_id") or 0)
    payload["product_id"] = int(payload.get("product_id") or 0)
    payload["attempt_count"] = int(payload.get("attempt_count") or 0)
    payload["request_headers"] = _json_obj(payload.get("request_headers"))
    payload["request_body"] = _json_obj(payload.get("request_body"))
    payload["response_body"] = _text(payload.get("response_body"))
    return payload


def _public_outbox(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["retry_count"] = int(payload.get("retry_count") or 0)
    payload["payload"] = _json_obj(payload.get("payload"))
    return payload


def _public_config(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["enabled"] = bool(payload.get("enabled"))
    payload["custom_params"] = _json_obj(payload.get("custom_params"))
    payload["has_secret"] = bool(_text(payload.get("secret")))
    payload.pop("secret", None)
    return payload


def _delivery_id() -> str:
    return "deliv_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]


def _retry_at(attempt_count: int) -> str | None:
    delays = {1: 0, 2: 60, 3: 300, 4: 1800, 5: 7200}
    if int(attempt_count) >= 5:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=delays.get(int(attempt_count) + 1, 7200))).isoformat()


def _get_order(conn: Any, order_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM wechat_pay_orders WHERE id = %s LIMIT 1", (int(order_id),)).fetchone()
    return dict(row) if row else None


def _get_product(conn: Any, product_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM wechat_pay_products WHERE id = %s LIMIT 1", (int(product_id),)).fetchone()
    return dict(row) if row else None


def _get_product_for_order(conn: Any, order: dict[str, Any]) -> dict[str, Any]:
    try:
        return _resolve_product_for_order(conn, order)
    except Exception:
        pass
    row = conn.execute(
        """
        SELECT *
        FROM wechat_pay_products
        WHERE product_code = %s
        LIMIT 1
        """,
        (_text(order.get("product_code")),),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "id": 0,
        "product_code": _text(order.get("product_code")),
        "name": _text(order.get("product_name") or order.get("product_code")),
        "amount_total": int(order.get("amount_total") or 0),
    }


def _get_config(conn: Any, config_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM external_push_config WHERE id = %s LIMIT 1", (int(config_id),)).fetchone()
    return dict(row) if row else None


def _get_product_config(conn: Any, product_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM external_push_config
        WHERE tenant_id = %s
          AND target_type = 'product'
          AND target_id = %s
          AND event_type = %s
        LIMIT 1
        """,
        (DEFAULT_TENANT_ID, str(int(product_id)), EVENT_TRANSACTION_PAID),
    ).fetchone()
    return dict(row) if row else None


def _get_delivery(conn: Any, delivery_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM external_push_delivery WHERE delivery_id = %s LIMIT 1", (_text(delivery_id),)).fetchone()
    return dict(row) if row else None


def _update_delivery_result(
    conn: Any,
    delivery_id: str,
    *,
    status: str,
    attempt_count: int,
    request_url: str,
    request_headers: dict[str, Any],
    request_body: dict[str, Any],
    response_status: int | None,
    response_body: str,
    error_message: str,
    next_retry_at: str | None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE external_push_delivery
        SET status = %s,
            attempt_count = %s,
            request_url = %s,
            request_headers = %s::jsonb,
            request_body = %s::jsonb,
            response_status = %s,
            response_body = %s,
            error_message = %s,
            next_retry_at = NULLIF(%s, '')::timestamptz,
            updated_at = CURRENT_TIMESTAMP
        WHERE delivery_id = %s
        RETURNING *
        """,
        (
            _text(status),
            int(attempt_count),
            _text(request_url),
            _jsonb(request_headers or {}),
            _jsonb(request_body or {}),
            response_status,
            _text(response_body),
            _text(error_message),
            _text(next_retry_at),
            _text(delivery_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def _create_test_delivery(conn: Any, *, config: dict[str, Any], product_id: int, request_url: str) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO external_push_delivery (
            tenant_id, config_id, event_type, delivery_id, target_type, target_id,
            order_id, product_id, status, attempt_count, request_url, request_headers,
            request_body, response_status, response_body, error_message, next_retry_at,
            created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, 'product', %s, 0, %s, 'pending', 0, %s, '{}'::jsonb, '{}'::jsonb, NULL, '', '', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            DEFAULT_TENANT_ID,
            int(config.get("id") or 0),
            EVENT_EXTERNAL_PUSH_TEST,
            _delivery_id(),
            str(int(product_id)),
            int(product_id),
            request_url,
        ),
    ).fetchone()
    return dict(row) if row else {}


def _create_order_delivery_once(
    conn: Any,
    *,
    config: dict[str, Any],
    order: dict[str, Any],
    product: dict[str, Any],
    request_url: str,
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO external_push_delivery (
            tenant_id, config_id, event_type, delivery_id, target_type, target_id,
            order_id, product_id, status, attempt_count, request_url, request_headers,
            request_body, response_status, response_body, error_message, next_retry_at,
            created_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s, 'product', %s, %s, %s, 'pending', 0, %s,
            '{}'::jsonb, '{}'::jsonb, NULL, '', '', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (config_id, order_id, event_type) WHERE order_id > 0
        DO UPDATE SET updated_at = external_push_delivery.updated_at
        RETURNING *
        """,
        (
            DEFAULT_TENANT_ID,
            int(config.get("id") or 0),
            EVENT_TRANSACTION_PAID,
            _delivery_id(),
            str(int(product.get("id") or 0)),
            int(order.get("id") or 0),
            int(product.get("id") or 0),
            request_url,
        ),
    ).fetchone()
    return dict(row) if row else {}


def _extract_external_effect_job_id(delivery: dict[str, Any]) -> int | None:
    response_body = _text(delivery.get("response_body"))
    if not response_body:
        return None
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        try:
            return int(payload.get("external_effect_job_id") or 0) or None
        except (TypeError, ValueError):
            return None
    if "external_effect_job_id=" in response_body:
        try:
            return int(response_body.rsplit("external_effect_job_id=", 1)[-1].strip())
        except (TypeError, ValueError):
            return None
    return None


def plan_order_paid_external_push_effect(
    conn: Any,
    *,
    order: dict[str, Any],
    transaction: dict[str, Any] | None = None,
    outbox: dict[str, Any] | None = None,
    source_module: str = "commerce.external_push_admin",
    source_route: str = "commerce.external_push_admin.plan_order_paid_external_push_effect",
) -> dict[str, Any]:
    """Create one configured External Effect Queue job for an order paid webhook.

    The order push must be config-driven. If the product has no enabled external
    push config, this returns a skipped result and intentionally does not create
    a half-populated webhook job.
    """

    order_payload = dict(order or {})
    product = _get_product_for_order(conn, order_payload)
    product_id = int(product.get("id") or 0)
    if not product_id:
        return {"ok": True, "queued": False, "skipped": True, "reason": "product_not_found"}
    config = _get_product_config(conn, product_id)
    if not config:
        return {"ok": True, "queued": False, "skipped": True, "reason": "external_push_config_not_found", "product_id": product_id}
    if not bool(config.get("enabled")):
        return {"ok": True, "queued": False, "skipped": True, "reason": "external_push_config_disabled", "config_id": config.get("id")}
    webhook_url = _text(config.get("webhook_url"))
    if not webhook_url:
        return {"ok": True, "queued": False, "skipped": True, "reason": "external_push_webhook_url_missing", "config_id": config.get("id")}
    delivery = _create_order_delivery_once(conn, config=config, order=order_payload, product=product, request_url=webhook_url)
    if int(delivery.get("attempt_count") or 0) > 0:
        return {
            "ok": True,
            "queued": True,
            "deduped": True,
            "delivery": _public_delivery(delivery),
            "external_effect_job_id": _extract_external_effect_job_id(delivery),
            "real_external_call_executed": False,
        }
    payload = _build_external_push_payload(
        EVENT_TRANSACTION_PAID,
        order_payload,
        product,
        _public_config(config),
        delivery_id=delivery["delivery_id"],
    )
    payload["transaction"] = {
        "transaction_id": _text((transaction or {}).get("transaction_id")),
        "trade_state": _text((transaction or {}).get("trade_state")),
        "success_time": _text((transaction or {}).get("success_time")),
    }
    if outbox:
        payload["domain_event_outbox_id"] = outbox.get("id")
    result = _attempt_delivery(conn, delivery, config=config, payload=payload, source_module=source_module, source_route=source_route)
    result["source_module"] = source_module
    result["source_route"] = source_route
    return result


def _attempt_delivery(
    conn: Any,
    delivery: dict[str, Any],
    *,
    config: dict[str, Any],
    payload: dict[str, Any],
    source_module: str = "commerce.external_push_admin",
    source_route: str = "commerce.external_push_admin._attempt_delivery",
) -> dict[str, Any]:
    delivery_id = _text(delivery.get("delivery_id"))
    event_type = _text(delivery.get("event_type")) or EVENT_TRANSACTION_PAID
    raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    headers = {
        "Content-Type": "application/json",
        "X-AICRM-Event": event_type,
        "X-AICRM-Delivery-Id": delivery_id,
        "X-AICRM-Timestamp": timestamp,
    }
    secret = _text(config.get("secret"))
    headers["X-AICRM-Signature"] = _sign_webhook_payload(secret, timestamp, raw_body) if secret else ""
    next_attempt = int(delivery.get("attempt_count") or 0) + 1
    request_url = _text(config.get("webhook_url") or delivery.get("request_url"))
    try:
        final_url = resolve_and_validate_public_https_url(request_url)
        effect_type = WEBHOOK_GENERIC_PUSH if event_type == EVENT_EXTERNAL_PUSH_TEST else WEBHOOK_ORDER_PAID_PUSH
        job = ExternalEffectService().plan_effect(
            effect_type=effect_type,
            adapter_name="outbound_webhook",
            operation="post",
            target_type="external_push_delivery",
            target_id=delivery_id,
            business_type="commerce_order" if event_type != EVENT_EXTERNAL_PUSH_TEST else "commerce_product_external_push_test",
            business_id=_text(delivery.get("order_id") or delivery.get("product_id") or delivery_id),
            payload={
                "webhook_url": final_url,
                "body": payload,
                "headers": headers,
                "legacy_delivery_id": delivery_id,
                "event_type": event_type,
            },
            payload_summary={
                "event_type": event_type,
                "delivery_id": delivery_id,
                "target_url_present": bool(final_url),
                "header_count": len(headers),
                "body_type": type(payload).__name__,
                "external_effect_queue_required": True,
            },
            context=CommandContext(
                actor_id="commerce_external_push",
                actor_type="system",
                request_id=delivery_id,
                trace_id=_text(delivery.get("delivery_id")),
                source_route=source_route,
            ),
            source_module=source_module,
            source_event_id=delivery_id,
            source_command_id=delivery_id,
            idempotency_key=f"commerce-external-push:{delivery_id}:{next_attempt}",
            execution_mode="execute",
            status="queued",
        )
        updated = _update_delivery_result(
            conn,
            delivery_id,
            status="retrying",
            attempt_count=next_attempt,
            request_url=final_url,
            request_headers=_redact_sensitive_fields(headers),
            request_body=_redact_sensitive_fields(payload),
            response_status=None,
            response_body=json.dumps({"external_effect_job_id": job.get("id")}, ensure_ascii=False),
            error_message="external_effect_job_queued",
            next_retry_at="",
        )
        return {
            "ok": True,
            "delivery": _public_delivery(updated),
            "external_effect_job_id": job.get("id"),
            "external_effect_required": True,
            "real_external_call_executed": False,
            "reason": "queued_external_effect_job",
        }
    except Exception as exc:
        updated = _update_delivery_result(
            conn,
            delivery_id,
            status="gave_up",
            attempt_count=next_attempt,
            request_url=request_url,
            request_headers=_redact_sensitive_fields(headers),
            request_body=_redact_sensitive_fields(payload),
            response_status=None,
            response_body="",
            error_message=_truncate_body(str(exc), 1000),
            next_retry_at="",
        )
        return {"ok": False, "delivery": _public_delivery(updated), "reason": str(exc)}


def list_order_external_push_state(order_id: int) -> dict[str, Any]:
    with _connect() as conn:
        order = _get_order(conn, int(order_id))
        if not order:
            raise ExternalPushAdminError("订单不存在")
        delivery_rows = conn.execute(
            """
            SELECT *
            FROM external_push_delivery
            WHERE tenant_id = %s
              AND order_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (DEFAULT_TENANT_ID, int(order_id)),
        ).fetchall()
        outbox_rows = conn.execute(
            """
            SELECT *
            FROM domain_event_outbox
            WHERE tenant_id = %s
              AND event_type = %s
              AND aggregate_type = 'wechat_pay_order'
              AND aggregate_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (DEFAULT_TENANT_ID, EVENT_TRANSACTION_PAID, str(int(order_id))),
        ).fetchall()
    return {
        "ok": True,
        "order_id": int(order_id),
        "outbox": [_public_outbox(dict(row)) for row in outbox_rows],
        "items": [_public_delivery(dict(row)) for row in delivery_rows],
    }


def send_product_external_push_test(product_id: int) -> dict[str, Any]:
    _record_legacy_marker("old_external_push_delivery_retry", metadata={"operation": "send_product_external_push_test", "product_id_present": bool(product_id)})
    with _connect() as conn:
        product = _get_product(conn, int(product_id))
        if not product:
            raise ExternalPushAdminError("商品不存在")
        config = _get_product_config(conn, int(product_id))
        if not config:
            raise ExternalPushAdminError("请先保存外部推送配置")
        config_public = _public_config(config)
        if not config_public.get("enabled"):
            raise ExternalPushAdminError("外部推送未启用")
        webhook_url = _text(config.get("webhook_url"))
        if not webhook_url:
            raise ExternalPushAdminError("webhook_url is required")
        delivery = _create_test_delivery(conn, config=config, product_id=int(product_id), request_url=webhook_url)
        payload = _build_external_push_payload(EVENT_EXTERNAL_PUSH_TEST, {}, product, config_public, delivery_id=delivery["delivery_id"])
        result = _attempt_delivery(conn, delivery, config=config, payload=payload)
        conn.commit()
        return result


def retry_order_delivery(order_id: int, delivery_id: str) -> dict[str, Any]:
    _record_legacy_marker("old_external_push_delivery_retry", metadata={"operation": "retry_order_delivery", "order_id_present": bool(order_id), "delivery_id_present": bool(delivery_id)})
    with _connect() as conn:
        order = _get_order(conn, int(order_id))
        if not order:
            raise ExternalPushAdminError("订单不存在")
        delivery = _get_delivery(conn, delivery_id)
        if not delivery or int(delivery.get("order_id") or 0) != int(order_id):
            raise ExternalPushAdminError("外推记录不存在")
        if _text(delivery.get("status")) not in {"failed", "retrying", "gave_up"}:
            raise ExternalPushAdminError("只能重试 failed / retrying / gave_up 状态")
        config = _get_config(conn, int(delivery.get("config_id") or 0)) or {}
        product = _get_product(conn, int(delivery.get("product_id") or 0)) or _get_product_for_order(conn, order)
        payload = _build_external_push_payload(EVENT_TRANSACTION_PAID, order, product, _public_config(config), delivery_id=delivery["delivery_id"])
        result = _attempt_delivery(conn, delivery, config=config, payload=payload)
        conn.commit()
        return result
