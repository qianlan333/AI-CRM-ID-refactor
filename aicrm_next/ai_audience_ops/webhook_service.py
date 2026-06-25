from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WECOM_MESSAGE_PRIVATE_SEND
from aicrm_next.shared.runtime_settings import runtime_bool

from .repository import AudienceRepository, build_audience_repository, _json_dumps, _text


class AudienceInboundWebhookService:
    def __init__(
        self,
        repository: AudienceRepository | None = None,
        external_effects: ExternalEffectService | None = None,
    ):
        self._repo = repository or build_audience_repository()
        self._external_effects = external_effects or ExternalEffectService()

    def handle(self, package_key: str, payload: dict[str, Any], *, raw_body: bytes, signature: str = "") -> dict[str, Any]:
        package = self._repo.get_package_by_key(package_key)
        if not package:
            return {"ok": False, "error": "package_not_found"}
        valid = self._verify(package, raw_body=raw_body, signature=signature)
        if not valid:
            return {"ok": False, "error": "invalid_signature"}
        normalized = dict(payload or {})
        normalized["idempotency_key"] = self._idempotency_key(package, normalized)
        external_effect_job_id = self._maybe_plan_action(package, normalized)
        recorded = self._repo.record_inbound_webhook(
            int(package["id"]),
            normalized,
            signature_valid=True,
            external_effect_job_id=external_effect_job_id,
        )
        return {
            "ok": True,
            "recorded": recorded,
            "external_effect_job_id": external_effect_job_id,
            "record_only": external_effect_job_id is None,
            "real_external_call_executed": False,
        }

    def _verify(self, package: dict[str, Any], *, raw_body: bytes, signature: str) -> bool:
        secret = _text(package.get("inbound_webhook_secret") or os.getenv("AICRM_AI_AUDIENCE_INBOUND_WEBHOOK_SECRET"))
        if not secret:
            return False
        provided = _text(signature)
        if provided.startswith("sha256="):
            provided = provided[len("sha256=") :]
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(provided, expected)

    def _idempotency_key(self, package: dict[str, Any], payload: dict[str, Any]) -> str:
        external_event_id = _text(payload.get("external_event_id"))
        if external_event_id:
            return f"ai_audience_inbound:{package['id']}:{external_event_id}"
        return f"ai_audience_inbound:{package['id']}:{hashlib.sha256(_json_dumps(payload).encode('utf-8')).hexdigest()}"

    def _maybe_plan_action(self, package: dict[str, Any], payload: dict[str, Any]) -> int | None:
        if not runtime_bool("AICRM_AI_AUDIENCE_INBOUND_ACTION_EXECUTE"):
            return None
        action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
        if _text(action.get("type")) != "send_private_message":
            return None
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        target = _text(action.get("target_external_userid"))
        sender = _text(action.get("sender_userid"))
        content = _text(message.get("text"))
        if not target or not sender or not content:
            return None
        job = self._external_effects.plan_effect(
            effect_type=WECOM_MESSAGE_PRIVATE_SEND,
            adapter_name="wecom_private_message",
            operation="send",
            target_type="external_user",
            target_id=target,
            payload={
                "channel": "wecom_private",
                "external_userids": [target],
                "owner_userid": sender,
                "content_text": content,
                "source": "ai_audience_inbound_webhook",
                **_test_scope(package),
            },
            payload_summary={
                "package_key": package.get("package_key"),
                "target_external_userid": target,
                "sender_userid": sender,
                "content_text_length": len(content),
            },
            business_type="ai_audience_inbound_webhook",
            business_id=_text(payload.get("external_event_id")),
            source_module="ai_audience_ops.webhook_service",
            idempotency_key=f"ai_audience_inbound_action:{package['id']}:{_text(payload.get('external_event_id'))}",
            execution_mode="execute",
            status="queued",
            context=CommandContext(actor_id="ai_audience_agent", actor_type="external_agent", source_route="ai_audience.inbound_webhook"),
        )
        return int(job.get("id") or 0) or None


def _test_scope(package: dict[str, Any]) -> dict[str, Any]:
    if _text(package.get("package_key")).startswith("prod_e2e_"):
        return {"is_test": True, "execution_scope": "test_loopback"}
    return {}
