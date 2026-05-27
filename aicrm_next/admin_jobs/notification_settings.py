from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from .domain import normalized_bool, normalized_text
from .repository import AdminJobsRepository, build_admin_jobs_repository

FEISHU_CHANNEL = "feishu"
FEISHU_VALIDATION_MESSAGE = "【群发队列监控验证】\n这是一条飞书 webhook 验证消息。收到此消息表示群发队列小时报配置成功。"
FEISHU_WEBHOOK_ERROR = "飞书 webhook 验证失败，请检查地址或机器人配置"
FEISHU_VALIDATION_STATUSES = {"unverified", "valid", "invalid"}
_ALLOWED_HOSTS = {"open.feishu.cn", "open.larksuite.com"}
_ALLOWED_PATH_PREFIX = "/open-apis/bot/v2/hook/"


class FeishuWebhookValidationError(ValueError):
    pass


def validate_feishu_webhook_url(webhook_url: str) -> None:
    value = normalized_text(webhook_url)
    if not value:
        raise FeishuWebhookValidationError("webhook 地址不能为空")
    try:
        parsed = urlsplit(value)
    except Exception as exc:
        raise FeishuWebhookValidationError("webhook 地址格式不正确") from exc
    if parsed.scheme != "https":
        raise FeishuWebhookValidationError("webhook 地址必须使用 https")
    hostname = normalized_text(parsed.hostname).lower()
    if not hostname:
        raise FeishuWebhookValidationError("webhook 地址域名不能为空")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise FeishuWebhookValidationError("webhook 地址域名不允许使用 IP")
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname not in _ALLOWED_HOSTS:
        raise FeishuWebhookValidationError("webhook 地址域名不在允许范围内")
    try:
        port = parsed.port
    except ValueError as exc:
        raise FeishuWebhookValidationError("webhook 地址端口不正确") from exc
    if port is not None:
        raise FeishuWebhookValidationError("webhook 地址不允许指定端口")
    if not parsed.path.startswith(_ALLOWED_PATH_PREFIX):
        raise FeishuWebhookValidationError("webhook 地址路径不正确")
    hook_token = parsed.path[len(_ALLOWED_PATH_PREFIX) :].strip("/")
    if not hook_token:
        raise FeishuWebhookValidationError("webhook hook token 不能为空")


def mask_webhook_url(webhook_url: str | None | Any) -> str | None:
    value = normalized_text(webhook_url)
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except Exception:
        return None
    hostname = normalized_text(parsed.hostname)
    if not parsed.scheme or not hostname or not parsed.path.startswith(_ALLOWED_PATH_PREFIX):
        return None
    token = parsed.path[len(_ALLOWED_PATH_PREFIX) :].strip("/")
    tail = token[-4:] if token else ""
    if not tail:
        return f"{parsed.scheme}://{hostname}{_ALLOWED_PATH_PREFIX}****"
    return f"{parsed.scheme}://{hostname}{_ALLOWED_PATH_PREFIX}****{tail}"


def public_feishu_notification_setting(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "enabled": False,
            "channel": FEISHU_CHANNEL,
            "webhookMasked": None,
            "validationStatus": "unconfigured",
            "validatedAt": None,
            "lastValidationError": None,
        }
    validation_status = normalized_text(row.get("validation_status")) or "unverified"
    if validation_status not in FEISHU_VALIDATION_STATUSES:
        validation_status = "unverified"
    return {
        "enabled": normalized_bool(row.get("enabled")),
        "channel": FEISHU_CHANNEL,
        "webhookMasked": mask_webhook_url(row.get("webhook_url")),
        "validationStatus": validation_status,
        "validatedAt": _iso_or_none(row.get("validated_at")),
        "lastValidationError": _short_error(row.get("last_validation_error")),
    }


def get_feishu_notification_setting(repo: AdminJobsRepository | None = None) -> dict[str, Any]:
    repo = repo or build_admin_jobs_repository()
    return public_feishu_notification_setting(repo.get_broadcast_notification_setting(FEISHU_CHANNEL))


def upsert_feishu_notification_setting(
    *,
    enabled: bool,
    webhook_url: str,
    validation_status: str = "unverified",
    validated_at: datetime | str | None = None,
    last_validation_error: str | None = None,
    repo: AdminJobsRepository | None = None,
) -> dict[str, Any]:
    validate_feishu_webhook_url(webhook_url)
    repo = repo or build_admin_jobs_repository()
    status = normalized_text(validation_status) or "unverified"
    if status not in FEISHU_VALIDATION_STATUSES:
        status = "unverified"
    row = repo.upsert_broadcast_notification_setting(
        channel=FEISHU_CHANNEL,
        enabled=bool(enabled),
        webhook_url=normalized_text(webhook_url),
        validation_status=status,
        validated_at=validated_at,
        last_validation_error=_short_error(last_validation_error),
    )
    return public_feishu_notification_setting(row)


def validate_feishu_webhook(
    *,
    webhook_url: str,
    enabled: bool = True,
    repo: AdminJobsRepository | None = None,
    sender: Callable[[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    repo = repo or build_admin_jobs_repository()
    try:
        validate_feishu_webhook_url(webhook_url)
    except FeishuWebhookValidationError:
        return {"ok": False, "validationStatus": "invalid", "message": FEISHU_WEBHOOK_ERROR}
    send = sender or send_feishu_webhook_message
    try:
        result = send(normalized_text(webhook_url), FEISHU_VALIDATION_MESSAGE)
    except Exception:
        result = {"ok": False}
    if result.get("ok") is True:
        now = datetime.now(timezone.utc)
        row = repo.upsert_broadcast_notification_setting(
            channel=FEISHU_CHANNEL,
            enabled=bool(enabled),
            webhook_url=normalized_text(webhook_url),
            validation_status="valid",
            validated_at=now,
            last_validation_error=None,
        )
        public = public_feishu_notification_setting(row)
        return {"ok": True, "validationStatus": "valid", "validatedAt": public["validatedAt"], "webhookMasked": public["webhookMasked"]}
    row = repo.upsert_broadcast_notification_setting(
        channel=FEISHU_CHANNEL,
        enabled=bool(enabled),
        webhook_url=normalized_text(webhook_url),
        validation_status="invalid",
        validated_at=None,
        last_validation_error=FEISHU_WEBHOOK_ERROR,
    )
    public = public_feishu_notification_setting(row)
    return {
        "ok": False,
        "validationStatus": "invalid",
        "message": FEISHU_WEBHOOK_ERROR,
        "webhookMasked": public["webhookMasked"],
        "lastValidationError": public["lastValidationError"],
    }


def send_feishu_webhook_message(webhook_url: str, text: str) -> dict[str, Any]:
    validate_feishu_webhook_url(webhook_url)
    import requests

    response = requests.post(
        normalized_text(webhook_url),
        json={"msg_type": "text", "content": {"text": normalized_text(text)}},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    if not (200 <= int(response.status_code) < 300):
        return {"ok": False, "status_code": int(response.status_code)}
    payload: dict[str, Any] = {}
    try:
        parsed = response.json()
        payload = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        payload = {}
    code = payload.get("code")
    status_code = payload.get("StatusCode")
    if code not in (None, 0) and str(code) != "0":
        return {"ok": False, "status_code": int(response.status_code)}
    if status_code not in (None, 0) and str(status_code) != "0":
        return {"ok": False, "status_code": int(response.status_code)}
    return {"ok": True, "status_code": int(response.status_code)}


def _short_error(value: Any) -> str | None:
    text = normalized_text(value)
    if not text:
        return None
    return text.replace("\n", " ")[:120]


def _iso_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    text = normalized_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        try:
            parsed_json = json.loads(json.dumps(text, default=str))
            return normalized_text(parsed_json) or None
        except Exception:
            return text[:80]
