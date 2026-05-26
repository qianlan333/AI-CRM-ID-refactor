from __future__ import annotations

import hashlib
import os
from typing import Any

from .audit import record_audit_event
from .wecom_group_contract import Json


def _mode() -> str:
    value = str(os.getenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "") or "").strip().lower()
    return value if value in {"disabled", "fake", "staging", "production"} else "disabled"


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(repr(sorted((payload or {}).items())).encode("utf-8")).hexdigest()[:24]


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload or {})
    safe.pop("token", None)
    safe.pop("access_token", None)
    return safe


class WeComGroupMessageAdapter:
    adapter_name = "WeComGroupMessageAdapter"

    def __init__(self, *, mode: str | None = None) -> None:
        self.mode = (mode or _mode()).strip().lower()
        if self.mode not in {"disabled", "fake", "staging", "production"}:
            self.mode = "disabled"

    def create_group_message_task(self, payload: dict[str, Any], *, idempotency_key: str = "") -> Json:
        normalized = self._build_wecom_payload(payload)
        target = {
            "sender": normalized.get("sender", ""),
            "chat_ids": list((payload or {}).get("chat_ids") or []),
            "payload_hash": _hash_payload(_safe_payload(normalized)),
        }
        audit = record_audit_event(
            adapter=self.adapter_name,
            operation="create_group_message_task",
            mode=self.mode,
            idempotency_key=idempotency_key or _hash_payload(target),
            side_effect_executed=False,
            status="blocked" if self.mode in {"disabled", "staging"} else "ok",
            error_code="wecom_group_message_disabled" if self.mode in {"disabled", "staging"} else "",
        )
        if self.mode in {"disabled", "staging"}:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "wecom_group_message_disabled",
                "error_message": "real WeCom customer-group message creation is disabled",
            }
        if self.mode == "fake":
            return {
                "ok": True,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": {"task_id": f"fake_group_msg_{target['payload_hash']}"},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "",
                "error_message": "",
            }
        if not _enabled("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE"):
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "production_guard_failed",
                "error_message": "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE is not enabled",
            }
        from .legacy_flask_facade import legacy_wecom_client_from_app

        result = legacy_wecom_client_from_app().create_group_message_task(normalized)
        return {
            "ok": True,
            "adapter": self.adapter_name,
            "mode": self.mode,
            "operation": "create_group_message_task",
            "idempotency_key": idempotency_key,
            "target": target,
            "result": result,
            "audit_id": audit["audit_id"],
            "side_effect_executed": True,
            "error_code": "",
            "error_message": "",
        }

    def _build_wecom_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        sender = str((payload or {}).get("sender") or "").strip()
        if not sender:
            raise ValueError("sender is required for WeCom group message")
        result = {
            "chat_type": "group",
            "sender": sender,
        }
        text = (payload or {}).get("text")
        if isinstance(text, dict) and str(text.get("content") or "").strip():
            result["text"] = {"content": str(text.get("content") or "").strip()}
        attachments = (payload or {}).get("attachments")
        if isinstance(attachments, list) and attachments:
            result["attachments"] = attachments
        chat_ids = [str(item or "").strip() for item in list((payload or {}).get("chat_ids") or []) if str(item or "").strip()]
        if chat_ids:
            result["chat_ids"] = chat_ids
        if not result.get("text") and not result.get("attachments"):
            raise ValueError("text or attachments is required for WeCom group message")
        return result


class LegacyBroadcastJobQueueGateway:
    def __init__(self, *, legacy_app_factory=None, enqueue_job_fn=None) -> None:
        self._legacy_app_factory = legacy_app_factory
        self._enqueue_job_fn = enqueue_job_fn

    def enqueue_group_message(
        self,
        *,
        plan_id: int,
        source_id: str,
        scheduled_at: str | None,
        owner_userid: str,
        chat_ids: list[str],
        content_payload: dict[str, Any],
        content_summary: str,
        created_by: str = "group_ops_webhook",
    ) -> int:
        def _enqueue() -> int:
            if self._enqueue_job_fn is None:
                from .legacy_flask_facade import legacy_broadcast_enqueue_job

                enqueue_job = legacy_broadcast_enqueue_job
            else:
                enqueue_job = self._enqueue_job_fn

            payload = dict(content_payload or {})
            payload["channel"] = "wecom_customer_group"
            payload["chat_ids"] = [str(item or "").strip() for item in chat_ids if str(item or "").strip()]
            payload["sender"] = str(owner_userid or "").strip()
            return enqueue_job(
                source_type="workflow",
                source_table="automation_group_ops_plans",
                source_id=str(source_id or plan_id),
                scheduled_for=scheduled_at,
                target_external_userids=[],
                target_summary=f"{len(payload['chat_ids'])} customer groups",
                content_type="wecom_customer_group",
                content_payload=payload,
                content_summary=str(content_summary or "")[:500],
                created_by=created_by,
                allow_empty_targets=True,
            )

        if self._legacy_app_factory is None:
            from .legacy_flask_facade import _legacy_app

            app = _legacy_app()
        else:
            app = self._legacy_app_factory()
        with app.app_context():
            return _enqueue()


def build_wecom_group_message_adapter() -> WeComGroupMessageAdapter:
    return WeComGroupMessageAdapter()


def build_group_ops_queue_gateway() -> LegacyBroadcastJobQueueGateway:
    return LegacyBroadcastJobQueueGateway()
