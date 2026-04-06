from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import requests
from flask import current_app

from ...infra.settings import get_setting
from . import repo


outbound_webhook_logger = logging.getLogger("outbound_webhook")

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_RETRY_SCHEDULED = "retry_scheduled"
STATUS_EXHAUSTED = "exhausted"

EVENT_OPENCLAW_FOCUS_MESSAGE = "openclaw_focus_message"
EVENT_QUESTIONNAIRE_SUBMIT = "questionnaire_submit"

_EVENT_CONFIGS = {
    EVENT_OPENCLAW_FOCUS_MESSAGE: {
        "url_key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL",
        "token_key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN",
        "timeout_key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "default_timeout": 10,
    },
    EVENT_QUESTIONNAIRE_SUBMIT: {
        "url_key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
        "token_key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN",
        "timeout_key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "default_timeout": 10,
    },
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _truncate_text(value: Any, *, maximum: int) -> str:
    text = _normalized_text(value)
    if len(text) <= maximum:
        return text
    return f"{text[:maximum]}..."


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_int(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def _setting_bool(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _event_config(event_type: str) -> dict[str, Any]:
    normalized = _normalized_text(event_type)
    config = _EVENT_CONFIGS.get(normalized)
    if not config:
        raise ValueError("unsupported outbound webhook event_type")
    return config


def _retry_enabled() -> bool:
    return _setting_bool("OUTBOUND_WEBHOOK_RETRY_ENABLED", default=True)


def _retry_max_attempts() -> int:
    return _setting_int("OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS", default=3, minimum=1)


def _retry_interval_seconds() -> int:
    return _setting_int("OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS", default=60, minimum=1)


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_retry_at(now_text: str) -> str:
    base = datetime.strptime(now_text, "%Y-%m-%d %H:%M:%S")
    return (base + timedelta(seconds=_retry_interval_seconds())).strftime("%Y-%m-%d %H:%M:%S")


def _response_body_summary(response: requests.Response) -> str:
    body_text = ""
    try:
        body_text = response.text
    except Exception:
        body_text = ""
    return _truncate_text(body_text, maximum=1000)


def _payload_summary(payload: dict[str, Any]) -> str:
    return _truncate_text(_json_dumps(payload), maximum=1000)


def _request_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if _normalized_text(token):
        headers["Authorization"] = f"Bearer {_normalized_text(token)}"
    return headers


def _delivery_snapshot(delivery: dict[str, Any]) -> dict[str, Any]:
    payload = _json_loads(delivery.get("payload_json"), default={})
    return {
        "id": int(delivery.get("id") or 0),
        "event_type": _normalized_text(delivery.get("event_type")),
        "source_key": _normalized_text(delivery.get("source_key")),
        "source_id": _normalized_text(delivery.get("source_id")),
        "target_url": _normalized_text(delivery.get("target_url")),
        "payload": payload if isinstance(payload, dict) else {},
        "payload_summary": _normalized_text(delivery.get("payload_summary")),
        "token_configured": bool(delivery.get("token_configured")),
        "status": _normalized_text(delivery.get("status")),
        "attempt_count": int(delivery.get("attempt_count") or 0),
        "max_attempts": int(delivery.get("max_attempts") or 0),
        "response_status_code": delivery.get("response_status_code"),
        "response_body_summary": _normalized_text(delivery.get("response_body_summary")),
        "last_error": _normalized_text(delivery.get("last_error")),
        "last_attempted_at": _normalized_text(delivery.get("last_attempted_at")),
        "next_retry_at": _normalized_text(delivery.get("next_retry_at")),
        "created_at": _normalized_text(delivery.get("created_at")),
        "updated_at": _normalized_text(delivery.get("updated_at")),
    }


def _attempt_delivery(delivery: dict[str, Any]) -> dict[str, Any]:
    snapshot = _delivery_snapshot(delivery)
    config = _event_config(snapshot["event_type"])
    webhook_url = _setting_text(config["url_key"])
    webhook_token = _setting_text(config["token_key"])
    timeout = _setting_int(config["timeout_key"], default=int(config["default_timeout"]), minimum=1)
    now_text = _iso_now()
    if not webhook_url:
        updated = repo.update_outbound_webhook_delivery(
            int(snapshot["id"]),
            target_url="",
            token_configured=bool(webhook_token),
            status=STATUS_FAILED,
            attempt_count=int(snapshot["attempt_count"]),
            response_status_code=None,
            response_body_summary="",
            last_error="webhook_not_configured",
            last_attempted_at=now_text,
            next_retry_at="",
        )
        return {
            "ok": False,
            "sent": False,
            "reason": "webhook_not_configured",
            "delivery": _delivery_snapshot(updated),
        }

    next_attempt = int(snapshot["attempt_count"]) + 1
    try:
        response = requests.post(
            webhook_url,
            json=snapshot["payload"],
            headers=_request_headers(webhook_token),
            timeout=timeout,
        )
        status_code = int(response.status_code)
        response_summary = _response_body_summary(response)
        if 200 <= status_code < 300:
            updated = repo.update_outbound_webhook_delivery(
                int(snapshot["id"]),
                target_url=webhook_url,
                token_configured=bool(webhook_token),
                status=STATUS_SUCCESS,
                attempt_count=next_attempt,
                response_status_code=status_code,
                response_body_summary=response_summary,
                last_error="",
                last_attempted_at=now_text,
                next_retry_at="",
            )
            outbound_webhook_logger.info(
                "outbound webhook success delivery_id=%s event_type=%s status_code=%s attempt=%s",
                snapshot["id"],
                snapshot["event_type"],
                status_code,
                next_attempt,
            )
            return {
                "ok": True,
                "sent": True,
                "status_code": status_code,
                "delivery": _delivery_snapshot(updated),
            }
        last_error = f"http_status_{status_code}"
        retryable = _retry_enabled() and next_attempt < int(snapshot["max_attempts"] or 0)
        updated = repo.update_outbound_webhook_delivery(
            int(snapshot["id"]),
            target_url=webhook_url,
            token_configured=bool(webhook_token),
            status=STATUS_RETRY_SCHEDULED if retryable else STATUS_EXHAUSTED,
            attempt_count=next_attempt,
            response_status_code=status_code,
            response_body_summary=response_summary,
            last_error=last_error,
            last_attempted_at=now_text,
            next_retry_at=_next_retry_at(now_text) if retryable else "",
        )
        outbound_webhook_logger.warning(
            "outbound webhook non-2xx delivery_id=%s event_type=%s status_code=%s attempt=%s retryable=%s",
            snapshot["id"],
            snapshot["event_type"],
            status_code,
            next_attempt,
            retryable,
        )
        return {
            "ok": False,
            "sent": False,
            "status_code": status_code,
            "reason": last_error,
            "delivery": _delivery_snapshot(updated),
        }
    except requests.RequestException as exc:
        retryable = _retry_enabled() and next_attempt < int(snapshot["max_attempts"] or 0)
        updated = repo.update_outbound_webhook_delivery(
            int(snapshot["id"]),
            target_url=webhook_url,
            token_configured=bool(webhook_token),
            status=STATUS_RETRY_SCHEDULED if retryable else STATUS_EXHAUSTED,
            attempt_count=next_attempt,
            response_status_code=None,
            response_body_summary="",
            last_error=_truncate_text(str(exc), maximum=500),
            last_attempted_at=now_text,
            next_retry_at=_next_retry_at(now_text) if retryable else "",
        )
        outbound_webhook_logger.exception(
            "outbound webhook failed delivery_id=%s event_type=%s attempt=%s retryable=%s",
            snapshot["id"],
            snapshot["event_type"],
            next_attempt,
            retryable,
        )
        return {
            "ok": False,
            "sent": False,
            "reason": str(exc),
            "delivery": _delivery_snapshot(updated),
        }


def send_outbound_webhook(
    *,
    event_type: str,
    payload: dict[str, Any],
    source_key: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    config = _event_config(event_type)
    webhook_url = _setting_text(config["url_key"])
    webhook_token = _setting_text(config["token_key"])
    delivery = repo.create_outbound_webhook_delivery(
        event_type=_normalized_text(event_type),
        source_key=_normalized_text(source_key),
        source_id=_normalized_text(source_id),
        target_url=webhook_url,
        payload_json=dict(payload or {}),
        payload_summary=_payload_summary(dict(payload or {})),
        token_configured=bool(webhook_token),
        max_attempts=_retry_max_attempts(),
    )
    return _attempt_delivery(delivery)


def retry_outbound_webhook_delivery(delivery_id: int) -> dict[str, Any]:
    delivery = repo.get_outbound_webhook_delivery(int(delivery_id))
    if not delivery:
        raise LookupError("delivery not found")
    if _normalized_text(delivery.get("status")) == STATUS_SUCCESS:
        raise ValueError("delivery already succeeded")
    return _attempt_delivery(delivery)


def run_due_outbound_webhook_retries(*, limit: int = 20) -> dict[str, Any]:
    now_text = _iso_now()
    due_deliveries = repo.list_due_outbound_webhook_deliveries(now_text=now_text, limit=limit)
    results = [_attempt_delivery(item) for item in due_deliveries]
    success_count = sum(1 for item in results if bool(item.get("ok")))
    return {
        "ok": True,
        "count": len(results),
        "scanned_count": len(due_deliveries),
        "retried_count": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "deliveries": results,
    }


def list_outbound_webhook_deliveries(
    *,
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    rows = repo.list_outbound_webhook_deliveries(
        event_type=_normalized_text(event_type),
        status=_normalized_text(status),
        limit=limit,
    )
    items = [_delivery_snapshot(row) for row in rows]
    return {
        "items": items,
        "count": len(items),
        "filters": {
            "event_type": _normalized_text(event_type),
            "status": _normalized_text(status),
            "limit": max(1, min(int(limit), 200)),
        },
    }


def get_outbound_webhook_delivery_counts() -> dict[str, int]:
    return repo.get_outbound_webhook_delivery_counts()
