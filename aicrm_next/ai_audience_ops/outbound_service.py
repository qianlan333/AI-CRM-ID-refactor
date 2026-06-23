from __future__ import annotations

import hashlib
from typing import Any

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_GENERIC_PUSH

from .repository import AudienceRepository, build_audience_repository, _text


class AudienceOutboundService:
    def __init__(
        self,
        repository: AudienceRepository | None = None,
        external_effects: ExternalEffectService | None = None,
    ):
        self._repo = repository or build_audience_repository()
        self._external_effects = external_effects or ExternalEffectService()

    def plan_for_member_event(self, member_event_id: int) -> dict[str, Any]:
        event = self._repo.get_member_event(int(member_event_id))
        if not event:
            return {"ok": False, "error": "member_event_not_found", "real_external_call_executed": False}
        package = self._repo.get_package(int(event["package_id"]))
        if not package:
            return {"ok": False, "error": "package_not_found", "real_external_call_executed": False}
        subscriptions = self._repo.list_subscriptions(
            int(package["id"]),
            active_only=True,
            trigger_event_type=_text(event.get("event_type")),
        )
        planned: list[dict[str, Any]] = []
        seen_targets: set[tuple[str, str, str]] = set()
        for subscription in subscriptions:
            if _text(subscription.get("target_type")) != "webhook":
                continue
            target_key = (
                _text(subscription.get("trigger_event_type")),
                _text(subscription.get("target_type")),
                _text(subscription.get("webhook_url")),
            )
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            payload = self._payload(package=package, member_event=event, subscription=subscription)
            target_hash = hashlib.sha256(f"{target_key[1]}:{target_key[2]}".encode("utf-8")).hexdigest()[:16]
            job = self._external_effects.plan_effect(
                effect_type=WEBHOOK_GENERIC_PUSH,
                adapter_name="webhook",
                operation="post",
                target_type="webhook",
                target_id=str(subscription["id"]),
                payload=payload,
                payload_summary={
                    "package_key": package.get("package_key"),
                    "member_event_id": int(event["id"]),
                    "trigger_event_type": event.get("event_type"),
                    "webhook_url_present": bool(subscription.get("webhook_url")),
                },
                business_type="ai_audience_member_event",
                business_id=str(event["id"]),
                source_module="ai_audience_ops.outbound_service",
                source_event_id=_text(event.get("internal_event_id")),
                risk_level="medium",
                requires_approval=bool(subscription.get("requires_approval")),
                execution_mode=_text(subscription.get("execution_mode")) or "execute",
                max_attempts=int(subscription.get("max_attempts") or 5),
                idempotency_key=f"ai_audience_outbound:{package['id']}:{event['id']}:{event.get('event_type')}:{target_hash}",
                status="queued",
                context=CommandContext(
                    actor_id="ai_audience_outbound",
                    actor_type="system",
                    source_route="ai_audience.member_event",
                    request_id=str(event["id"]),
                ),
            )
            planned.append(job)
        return {
            "ok": True,
            "member_event_id": int(event["id"]),
            "planned_count": len(planned),
            "external_effect_jobs": planned,
            "real_external_call_executed": False,
        }

    def _payload(self, *, package: dict[str, Any], member_event: dict[str, Any], subscription: dict[str, Any]) -> dict[str, Any]:
        member = {
            "identity_type": member_event.get("identity_type"),
            "identity_value": member_event.get("identity_value"),
            "person_id": member_event.get("person_id"),
            "external_userid": member_event.get("external_userid"),
            "mobile_hash": member_event.get("mobile_hash"),
            "owner_userid": member_event.get("owner_userid"),
        }
        body = {
            "event_type": f"audience.member.{member_event.get('event_type')}",
            "package_key": package.get("package_key"),
            "package_name": package.get("name"),
            "member_event_id": int(member_event["id"]),
            "member": member,
            "payload": member_event.get("payload_json") or {},
            "idempotency_key": member_event.get("idempotency_key"),
        }
        headers = subscription.get("headers_json") if isinstance(subscription.get("headers_json"), dict) else {}
        return {
            "webhook_url": subscription.get("webhook_url"),
            "signing_secret": subscription.get("signing_secret"),
            "headers": headers,
            "body": body,
        }
