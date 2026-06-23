from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from aicrm_next.shared.runtime_settings import runtime_bool, runtime_csv, runtime_setting

from .repository import AudienceRepository, build_audience_repository, _json_dumps, _text
from .webhook_service import AudienceInboundWebhookService


TEST_AGENT_MESSAGE_TEXT = "【AI人群包生产真实测试】你好，这是一条由 AI 人群包自测 Agent 生成的测试消息。"


class AudienceTestAgentService:
    def __init__(
        self,
        repository: AudienceRepository | None = None,
        inbound_service: AudienceInboundWebhookService | None = None,
    ):
        self._repo = repository or build_audience_repository()
        self._inbound = inbound_service or AudienceInboundWebhookService(repository=self._repo)

    def handle(self, payload: dict[str, Any], *, signature: str = "") -> dict[str, Any]:
        if not runtime_bool("AICRM_AI_AUDIENCE_TEST_AGENT_ENABLED"):
            return {"ok": False, "error": "test_agent_disabled", "status_code": 404, "real_external_call_executed": False}

        package_key = _text(payload.get("package_key"))
        member_event_id = int(payload.get("member_event_id") or 0)
        event_type = _event_type(payload)
        member = payload.get("member") if isinstance(payload.get("member"), dict) else {}
        external_userid = _text(member.get("external_userid") or member.get("identity_value"))

        if not package_key or not member_event_id or not event_type or not external_userid:
            return {"ok": False, "error": "invalid_test_agent_payload", "status_code": 400, "real_external_call_executed": False}
        if not _allowed("AICRM_AI_AUDIENCE_TEST_AGENT_PACKAGE_KEYS", package_key):
            return {"ok": False, "error": "package_key_not_allowed", "status_code": 403, "real_external_call_executed": False}
        if not _allowed("AICRM_AI_AUDIENCE_TEST_AGENT_ALLOWED_EXTERNAL_USERIDS", external_userid):
            return {"ok": False, "error": "external_userid_not_allowed", "status_code": 403, "real_external_call_executed": False}

        package = self._repo.get_package_by_key(package_key)
        if not package:
            return {"ok": False, "error": "package_not_found", "status_code": 404, "real_external_call_executed": False}
        subscription = self._matching_subscription(
            int(package["id"]),
            event_type=event_type,
            payload=payload,
            signature=signature,
        )
        if not subscription:
            return {"ok": False, "error": "invalid_signature", "status_code": 401, "real_external_call_executed": False}

        sender = _text(runtime_setting("AICRM_AI_AUDIENCE_TEST_AGENT_SENDER_USERID", "HuangYouCan")) or "HuangYouCan"
        callback_payload = {
            "external_event_id": f"self_agent:{package_key}:{member_event_id}",
            "member_event_id": member_event_id,
            "status": "generated",
            "message": {"text": TEST_AGENT_MESSAGE_TEXT},
            "action": {
                "type": "send_private_message",
                "target_external_userid": external_userid,
                "sender_userid": sender,
            },
        }
        inbound_secret = _text(package.get("inbound_webhook_secret") or os.getenv("AICRM_AI_AUDIENCE_INBOUND_WEBHOOK_SECRET"))
        if not inbound_secret:
            return {"ok": False, "error": "inbound_webhook_secret_missing", "status_code": 400, "real_external_call_executed": False}
        raw_body = _json_dumps(callback_payload).encode("utf-8")
        inbound_signature = hmac.new(inbound_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        result = self._inbound.handle(package_key, callback_payload, raw_body=raw_body, signature=inbound_signature)
        status_code = 200 if result.get("ok") else 400
        return {
            "ok": bool(result.get("ok")),
            "status_code": status_code,
            "package_key": package_key,
            "member_event_id": member_event_id,
            "external_userid": external_userid,
            "sender_userid": sender,
            "simulated_message": TEST_AGENT_MESSAGE_TEXT,
            "inbound_result": result,
            "external_effect_job_id": result.get("external_effect_job_id"),
            "record_only": result.get("record_only"),
            "real_external_call_executed": False,
        }

    def _matching_subscription(self, package_id: int, *, event_type: str, payload: dict[str, Any], signature: str) -> dict[str, Any] | None:
        for subscription in self._repo.list_subscriptions(package_id, active_only=True, trigger_event_type=event_type):
            secret = _text(subscription.get("signing_secret"))
            if secret and _external_effect_signature_valid(secret=secret, payload=payload, signature=signature):
                return subscription
        return None


def _event_type(payload: dict[str, Any]) -> str:
    raw = _text(payload.get("event_type"))
    if raw.startswith("audience.member."):
        return raw.rsplit(".", 1)[-1]
    return raw


def _allowed(setting_name: str, value: str) -> bool:
    allowed = runtime_csv(setting_name)
    return bool(value and value in allowed)


def _external_effect_signature_valid(*, secret: str, payload: dict[str, Any], signature: str) -> bool:
    provided = _text(signature)
    if provided.startswith("sha256="):
        provided = provided[len("sha256=") :]
    if not secret or not provided:
        return False
    canonical = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)
