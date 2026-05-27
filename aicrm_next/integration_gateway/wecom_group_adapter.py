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


def _fake_group_chat_snapshots(owner_userid: str) -> list[dict[str, Any]]:
    rows = [
        {
            "chat_id": "wrOgAAA001",
            "group_name": "体验课 01 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "internal_member_count": 12,
            "external_member_count": 150,
            "status": "active",
        },
        {
            "chat_id": "wrOgAAA002",
            "group_name": "体验课 02 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "internal_member_count": 10,
            "external_member_count": 160,
            "status": "active",
        },
        {
            "chat_id": "wrOgAAA003",
            "group_name": "体验课 03 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "internal_member_count": 9,
            "external_member_count": 176,
            "status": "active",
        },
        {
            "chat_id": "wrOgBBB001",
            "group_name": "成交陪跑 01 群",
            "owner_userid": "owner_002",
            "owner_name": "李小红",
            "internal_member_count": 8,
            "external_member_count": 88,
            "status": "active",
        },
    ]
    owner = str(owner_userid or "").strip()
    return [dict(item) for item in rows if not owner or item["owner_userid"] == owner]


def _member_counts(member_list: list[dict[str, Any]]) -> tuple[int, int]:
    internal = 0
    external = 0
    for member in member_list:
        member_type = int(member.get("type") or 0)
        if member_type == 1 or (member.get("userid") and not member.get("unionid")):
            internal += 1
        else:
            external += 1
    return internal, external


def _normalize_group_chat_detail(detail: dict[str, Any], *, fallback_owner_userid: str = "") -> dict[str, Any]:
    group_chat = detail.get("group_chat") if isinstance(detail.get("group_chat"), dict) else detail
    members = group_chat.get("member_list") if isinstance(group_chat.get("member_list"), list) else []
    internal, external = _member_counts([item for item in members if isinstance(item, dict)])
    owner_userid = str(group_chat.get("owner") or group_chat.get("owner_userid") or fallback_owner_userid or "").strip()
    return {
        "chat_id": str(group_chat.get("chat_id") or "").strip(),
        "group_name": str(group_chat.get("name") or group_chat.get("group_name") or group_chat.get("chat_id") or "").strip(),
        "owner_userid": owner_userid,
        "owner_name": str(group_chat.get("owner_name") or owner_userid).strip(),
        "internal_member_count": internal,
        "external_member_count": external,
        "status": "active",
    }


class WeComGroupChatSyncAdapter:
    adapter_name = "WeComGroupChatSyncAdapter"

    def __init__(self, *, mode: str | None = None) -> None:
        self.mode = (mode or _mode()).strip().lower()
        if self.mode not in {"disabled", "fake", "staging", "production"}:
            self.mode = "disabled"

    def list_group_chats(self, *, owner_userid: str, limit: int = 100, cursor: str = "") -> Json:
        owner = str(owner_userid or "").strip()
        page_size = max(1, min(int(limit or 100), 200))
        audit = record_audit_event(
            adapter=self.adapter_name,
            operation="list_group_chats",
            mode=self.mode,
            idempotency_key=_hash_payload({"owner_userid": owner, "limit": page_size, "cursor": cursor}),
            side_effect_executed=False,
            status="blocked" if self.mode in {"disabled", "staging"} else "ok",
            error_code="wecom_group_sync_disabled" if self.mode in {"disabled", "staging"} else "",
        )
        if self.mode in {"disabled", "staging"}:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "list_group_chats",
                "groups": [],
                "next_cursor": "",
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "wecom_group_sync_disabled",
                "error_message": "real WeCom customer-group sync is disabled",
            }
        if self.mode == "fake":
            groups = _fake_group_chat_snapshots(owner)[:page_size]
            return {
                "ok": True,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "list_group_chats",
                "groups": groups,
                "next_cursor": "",
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "",
                "error_message": "",
            }
        if not _enabled("AICRM_ENABLE_REAL_WECOM_GROUP_SYNC"):
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "list_group_chats",
                "groups": [],
                "next_cursor": "",
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "production_guard_failed",
                "error_message": "AICRM_ENABLE_REAL_WECOM_GROUP_SYNC is not enabled",
            }

        from .legacy_flask_facade import legacy_wecom_client_from_app

        client = legacy_wecom_client_from_app()
        list_payload = {
            "status_filter": 0,
            "owner_filter": {"userid_list": [owner]} if owner else {},
            "cursor": str(cursor or ""),
            "limit": page_size,
        }
        list_result = client.list_group_chats(list_payload)
        groups: list[dict[str, Any]] = []
        for item in list_result.get("group_chat_list") or []:
            chat_id = str((item or {}).get("chat_id") or "").strip()
            if not chat_id:
                continue
            detail = self.get_group_chat(chat_id, owner_userid=owner)
            if detail.get("ok") and detail.get("group"):
                groups.append(dict(detail["group"]))
        return {
            "ok": True,
            "adapter": self.adapter_name,
            "mode": self.mode,
            "operation": "list_group_chats",
            "groups": groups,
            "next_cursor": str(list_result.get("next_cursor") or ""),
            "audit_id": audit["audit_id"],
            "side_effect_executed": True,
            "error_code": "",
            "error_message": "",
        }

    def get_group_chat(self, chat_id: str, *, owner_userid: str = "") -> Json:
        chat = str(chat_id or "").strip()
        owner = str(owner_userid or "").strip()
        audit = record_audit_event(
            adapter=self.adapter_name,
            operation="get_group_chat",
            mode=self.mode,
            idempotency_key=_hash_payload({"chat_id": chat, "owner_userid": owner}),
            side_effect_executed=False,
            status="blocked" if self.mode in {"disabled", "staging"} else "ok",
            error_code="wecom_group_sync_disabled" if self.mode in {"disabled", "staging"} else "",
        )
        if self.mode in {"disabled", "staging"}:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "get_group_chat",
                "group": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "wecom_group_sync_disabled",
                "error_message": "real WeCom customer-group sync is disabled",
            }
        if self.mode == "fake":
            group = next((item for item in _fake_group_chat_snapshots(owner) if item["chat_id"] == chat), None)
            return {
                "ok": bool(group),
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "get_group_chat",
                "group": dict(group or {}),
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "" if group else "not_found",
                "error_message": "" if group else "fake group chat not found",
            }
        if not _enabled("AICRM_ENABLE_REAL_WECOM_GROUP_SYNC"):
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "get_group_chat",
                "group": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "production_guard_failed",
                "error_message": "AICRM_ENABLE_REAL_WECOM_GROUP_SYNC is not enabled",
            }
        from .legacy_flask_facade import legacy_wecom_client_from_app

        result = legacy_wecom_client_from_app().get_group_chat(chat)
        return {
            "ok": True,
            "adapter": self.adapter_name,
            "mode": self.mode,
            "operation": "get_group_chat",
            "group": _normalize_group_chat_detail(result, fallback_owner_userid=owner),
            "audit_id": audit["audit_id"],
            "side_effect_executed": True,
            "error_code": "",
            "error_message": "",
        }


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


class LegacyGroupOpsQueueStatsGateway:
    def __init__(self, *, legacy_app_factory=None, list_jobs_fn=None) -> None:
        self._legacy_app_factory = legacy_app_factory
        self._list_jobs_fn = list_jobs_fn

    def count_group_ops_queue(self) -> int:
        def _list() -> list[dict[str, Any]]:
            if self._list_jobs_fn is not None:
                return list(self._list_jobs_fn())
            from wecom_ability_service.domains.broadcast_jobs.service import list_jobs

            return list(list_jobs(statuses=["queued", "waiting_approval", "claimed"], source_types=["workflow"], limit=1000, offset=0))

        if self._legacy_app_factory is None:
            from .legacy_flask_facade import _legacy_app

            app = _legacy_app()
        else:
            app = self._legacy_app_factory()
        with app.app_context():
            count = 0
            for job in _list():
                payload = job.get("content_payload") if isinstance(job.get("content_payload"), dict) else {}
                if job.get("source_table") == "automation_group_ops_plans" or payload.get("channel") == "wecom_customer_group":
                    count += 1
            return count


def build_wecom_group_message_adapter() -> WeComGroupMessageAdapter:
    return WeComGroupMessageAdapter()


def build_wecom_group_chat_sync_adapter() -> WeComGroupChatSyncAdapter:
    return WeComGroupChatSyncAdapter()


def build_group_ops_queue_gateway() -> LegacyBroadcastJobQueueGateway:
    return LegacyBroadcastJobQueueGateway()


def build_group_ops_queue_stats_gateway() -> LegacyGroupOpsQueueStatsGateway:
    return LegacyGroupOpsQueueStatsGateway()
