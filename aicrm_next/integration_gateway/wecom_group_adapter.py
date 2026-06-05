from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from aicrm_next.automation_engine.group_ops.domain import normalize_group_admin_userids
from aicrm_next.shared.postgres_connection import get_db

from .audit import record_audit_event
from .wecom_group_contract import Json

WECOM_GROUP_CHAT_ID_LIST_FIELD = "chat_id_list"


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


def _requested_chat_ids(payload: dict[str, Any]) -> list[str]:
    return [str(item or "").strip() for item in list((payload or {}).get("chat_ids") or []) if str(item or "").strip()]


class NextWeComGroupClient:
    def __init__(self, *, access_token: str | None = None, request_fn: Any = None, base_url: str = "https://qyapi.weixin.qq.com") -> None:
        self._access_token = str(access_token or os.getenv("AICRM_WECOM_ACCESS_TOKEN") or os.getenv("WECOM_ACCESS_TOKEN") or os.getenv("WEWORK_ACCESS_TOKEN") or "").strip()
        self._request_fn = request_fn
        self._base_url = str(base_url or "").rstrip("/")

    def list_group_chats(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/cgi-bin/externalcontact/groupchat/list", payload)

    def get_group_chat(self, chat_id: str, need_name: int = 1) -> dict[str, Any]:
        return self._post("/cgi-bin/externalcontact/groupchat/get", {"chat_id": str(chat_id or "").strip(), "need_name": int(need_name or 1)})

    def create_group_message_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/cgi-bin/externalcontact/add_msg_template", payload)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._request_fn is not None:
            return dict(self._request_fn(path=path, payload=dict(payload or {})) or {})
        if not self._access_token:
            return {"errcode": -1, "errmsg": "next_wecom_group_client_not_configured: access token is required"}
        from urllib import request
        from urllib.error import URLError

        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        url = f"{self._base_url}{path}?access_token={self._access_token}"
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with request.urlopen(req, timeout=15) as resp:
                return dict(json.loads(resp.read().decode("utf-8") or "{}"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            return {"errcode": -1, "errmsg": f"next_wecom_group_client_request_failed: {exc}"}


class GroupMessageTaskAdapter:
    adapter_name = "GroupMessageTaskAdapter"

    def __init__(self, *, mode: str | None = None, client: NextWeComGroupClient | None = None) -> None:
        self.mode = (mode or _mode()).strip().lower()
        if self.mode not in {"disabled", "fake", "staging", "production"}:
            self.mode = "disabled"
        self._client = client or NextWeComGroupClient()

    def create_group_message_task(self, payload: dict[str, Any], *, idempotency_key: str = "") -> Json:
        normalized = self._build_wecom_payload(payload)
        requested_chat_ids = list(normalized.get(WECOM_GROUP_CHAT_ID_LIST_FIELD) or [])
        target = {
            "sender": normalized.get("sender", ""),
            "requested_chat_ids": requested_chat_ids,
            "requested_chat_count": len(requested_chat_ids),
            "exact_target_required": True,
            "official_chat_id_field": WECOM_GROUP_CHAT_ID_LIST_FIELD,
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
                "status": "blocked",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": requested_chat_ids,
                "error_code": "wecom_group_message_disabled",
                "error_message": "real WeCom customer-group message creation is disabled",
            }
        if self.mode == "fake":
            return {
                "ok": True,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "status": "blocked",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": {
                    "task_id": f"fake_group_msg_{target['payload_hash']}",
                    "requested_chat_ids": requested_chat_ids,
                    "requested_chat_count": len(requested_chat_ids),
                },
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "exact_target_required": True,
                "exact_target_verified": True,
                "exact_target_verification_source": "fake_adapter_requested_chat_ids",
                "requested_chat_ids": requested_chat_ids,
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
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": requested_chat_ids,
                "error_code": "production_guard_failed",
                "error_message": "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE is not enabled",
            }
        result = self._client.create_group_message_task(normalized)
        errcode = int(result.get("errcode") or 0) if isinstance(result, dict) else -1
        msgid = str((result or {}).get("msgid") or "").strip() if isinstance(result, dict) else ""
        failed_chat_ids = [
            str(item or "").strip()
            for item in list((result or {}).get("fail_list") or [])
            if str(item or "").strip()
        ] if isinstance(result, dict) else []
        if errcode != 0:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": result,
                "audit_id": audit["audit_id"],
                "side_effect_executed": True,
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": requested_chat_ids,
                "error_code": "wecom_group_message_api_error",
                "error_message": str((result or {}).get("errmsg") or "WeCom group message API failed"),
            }
        if not msgid:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": result,
                "audit_id": audit["audit_id"],
                "side_effect_executed": True,
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": requested_chat_ids,
                "error_code": "wecom_group_exact_target_not_verified",
                "error_message": "WeCom did not return msgid for exact target verification",
            }
        if failed_chat_ids:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "create_group_message_task",
                "idempotency_key": idempotency_key,
                "target": target,
                "result": result,
                "audit_id": audit["audit_id"],
                "side_effect_executed": True,
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": requested_chat_ids,
                "requested_chat_count": len(requested_chat_ids),
                "failed_chat_ids": failed_chat_ids,
                "failed_chat_count": len(failed_chat_ids),
                "wecom_msgid": msgid,
                "error_code": "wecom_group_message_partial_failure",
                "error_message": f"WeCom rejected {len(failed_chat_ids)} requested customer-group targets",
            }
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
            "exact_target_required": True,
            "exact_target_verified": True,
            "exact_target_verification_source": f"wecom_add_msg_template.{WECOM_GROUP_CHAT_ID_LIST_FIELD}",
            "requested_chat_ids": requested_chat_ids,
            "requested_chat_count": len(requested_chat_ids),
            "wecom_msgid": msgid,
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
        chat_ids = _requested_chat_ids(payload)
        if not chat_ids:
            raise ValueError("chat_ids is required for exact WeCom customer-group targeting")
        # Official WeCom add_msg_template group targeting field is chat_id_list.
        # Keep internal chat_ids out of the outgoing request so WeCom cannot
        # ignore it and fall back to sender-wide customer groups.
        result[WECOM_GROUP_CHAT_ID_LIST_FIELD] = chat_ids
        result["allow_select"] = False
        if not result.get("text") and not result.get("attachments"):
            raise ValueError("text or attachments is required for WeCom group message")
        return result


class WeComGroupMessageAdapter(GroupMessageTaskAdapter):
    adapter_name = "WeComGroupMessageAdapter"


def _fake_group_chat_snapshots(owner_userid: str) -> list[dict[str, Any]]:
    rows = [
        {
            "chat_id": "wrOgAAA001",
            "group_name": "体验课 01 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "admin_userids": [],
            "internal_member_count": 12,
            "external_member_count": 150,
            "status": "active",
        },
        {
            "chat_id": "wrOgAAA002",
            "group_name": "体验课 02 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "admin_userids": [],
            "internal_member_count": 10,
            "external_member_count": 160,
            "status": "active",
        },
        {
            "chat_id": "wrOgAAA003",
            "group_name": "体验课 03 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "admin_userids": [],
            "internal_member_count": 9,
            "external_member_count": 176,
            "status": "active",
        },
        {
            "chat_id": "wrOgBBB001",
            "group_name": "成交陪跑 01 群",
            "owner_userid": "owner_002",
            "owner_name": "李小红",
            "admin_userids": ["admin_001"],
            "internal_member_count": 8,
            "external_member_count": 88,
            "status": "active",
        },
    ]
    owner = str(owner_userid or "").strip()
    return [dict(item) for item in rows if not owner or item["owner_userid"] == owner]


def _member_counts(member_list: list[Any]) -> tuple[int, int, int, list[str]]:
    internal = 0
    external = 0
    skipped = 0
    warnings: list[str] = []
    for member in member_list:
        if not isinstance(member, dict):
            skipped += 1
            warnings.append("skipped malformed group member")
            continue
        try:
            member_type = int(member.get("type") or 0)
            if member_type == 1 or (member.get("userid") and not member.get("unionid")):
                internal += 1
            else:
                external += 1
        except (TypeError, ValueError):
            skipped += 1
            warnings.append("skipped group member with invalid type")
    return internal, external, skipped, warnings


def _normalize_group_chat_detail(detail: dict[str, Any], *, fallback_owner_userid: str = "") -> dict[str, Any]:
    group_chat = detail.get("group_chat") if isinstance(detail.get("group_chat"), dict) else detail
    members = group_chat.get("member_list") if isinstance(group_chat.get("member_list"), list) else []
    internal, external, skipped, warnings = _member_counts(members)
    owner_userid = str(group_chat.get("owner") or group_chat.get("owner_userid") or fallback_owner_userid or "").strip()
    return {
        "chat_id": str(group_chat.get("chat_id") or "").strip(),
        "group_name": str(group_chat.get("name") or group_chat.get("group_name") or group_chat.get("chat_id") or "").strip(),
        "owner_userid": owner_userid,
        "owner_name": str(group_chat.get("owner_name") or owner_userid).strip(),
        "admin_userids": normalize_group_admin_userids(group_chat.get("admin_list") or group_chat.get("admin_userids")),
        "internal_member_count": internal,
        "external_member_count": external,
        "skipped_member_count": skipped,
        "warnings": warnings,
        "status": "active",
    }


class CustomerGroupAssetRepository:
    def __init__(self, *, client: NextWeComGroupClient | None = None) -> None:
        self._client = client or NextWeComGroupClient()

    def list_group_chats(self, *, owner_userid: str, limit: int = 100, cursor: str = "") -> tuple[list[dict[str, Any]], str, int, list[str]]:
        owner = str(owner_userid or "").strip()
        page_size = max(1, min(int(limit or 100), 200))
        list_payload = {
            "status_filter": 0,
            "owner_filter": {"userid_list": [owner]} if owner else {},
            "cursor": str(cursor or ""),
            "limit": page_size,
        }
        list_result = self._client.list_group_chats(list_payload)
        errcode = int(list_result.get("errcode") or 0)
        if errcode != 0:
            raise RuntimeError(str(list_result.get("errmsg") or "WeCom group list failed"))
        groups: list[dict[str, Any]] = []
        warnings: list[str] = []
        skipped_count = 0
        for item in list_result.get("group_chat_list") or []:
            chat_id = str((item or {}).get("chat_id") or "").strip()
            if not chat_id:
                skipped_count += 1
                warnings.append("skipped group chat without chat_id")
                continue
            detail = self.get_group_chat(chat_id=chat_id, owner_userid=owner)
            if detail:
                group = dict(detail)
                skipped_count += int(group.pop("skipped_member_count", 0) or 0)
                warnings.extend([str(item) for item in group.pop("warnings", []) if str(item or "").strip()])
                groups.append(group)
            else:
                skipped_count += 1
                warnings.append(f"skipped group chat {chat_id}")
        return groups, str(list_result.get("next_cursor") or ""), skipped_count, warnings

    def get_group_chat(self, *, chat_id: str, need_name: int = 1, owner_userid: str = "") -> dict[str, Any]:
        result = self._client.get_group_chat(str(chat_id or "").strip(), need_name=need_name)
        errcode = int(result.get("errcode") or 0)
        if errcode != 0:
            raise RuntimeError(str(result.get("errmsg") or "WeCom group detail failed"))
        return _normalize_group_chat_detail(result, fallback_owner_userid=owner_userid)


class WeComGroupAssetAdapter:
    adapter_name = "WeComGroupAssetAdapter"

    def __init__(self, *, mode: str | None = None, repository: CustomerGroupAssetRepository | None = None, client: NextWeComGroupClient | None = None) -> None:
        self.mode = (mode or _mode()).strip().lower()
        if self.mode not in {"disabled", "fake", "staging", "production"}:
            self.mode = "disabled"
        self._repository = repository or CustomerGroupAssetRepository(client=client)

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
                "status": "blocked",
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
                "status": "blocked",
                "groups": [],
                "next_cursor": "",
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "production_guard_failed",
                "error_message": "AICRM_ENABLE_REAL_WECOM_GROUP_SYNC is not enabled",
            }

        try:
            groups, next_cursor, skipped_count, warnings = self._repository.list_group_chats(owner_userid=owner, limit=page_size, cursor=cursor)
        except Exception as exc:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "list_group_chats",
                "groups": [],
                "next_cursor": "",
                "audit_id": audit["audit_id"],
                "side_effect_executed": True,
                "error_code": "wecom_group_list_failed",
                "error_message": str(exc),
            }
        return {
            "ok": True,
            "adapter": self.adapter_name,
            "mode": self.mode,
            "operation": "list_group_chats",
            "groups": groups,
            "next_cursor": next_cursor,
            "audit_id": audit["audit_id"],
            "side_effect_executed": True,
            "skipped_count": skipped_count,
            "warnings": warnings,
            "error_code": "",
            "error_message": "",
        }

    def get_group_chat(self, chat_id: str = "", *, need_name: int = 1, owner_userid: str = "") -> Json:
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
                "status": "blocked",
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
                "status": "blocked",
                "group": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": False,
                "error_code": "production_guard_failed",
                "error_message": "AICRM_ENABLE_REAL_WECOM_GROUP_SYNC is not enabled",
            }
        try:
            group = self._repository.get_group_chat(chat_id=chat, need_name=need_name, owner_userid=owner)
        except Exception as exc:
            return {
                "ok": False,
                "adapter": self.adapter_name,
                "mode": self.mode,
                "operation": "get_group_chat",
                "group": {},
                "audit_id": audit["audit_id"],
                "side_effect_executed": True,
                "error_code": "wecom_group_detail_failed",
                "error_message": str(exc),
            }
        return {
            "ok": True,
            "adapter": self.adapter_name,
            "mode": self.mode,
            "operation": "get_group_chat",
            "group": group,
            "audit_id": audit["audit_id"],
            "side_effect_executed": True,
            "error_code": "",
            "error_message": "",
        }


class WeComGroupChatSyncAdapter(WeComGroupAssetAdapter):
    adapter_name = "WeComGroupChatSyncAdapter"


class NextGroupOpsQueueGateway:
    def __init__(self, *, insert_job_fn=None) -> None:
        self._insert_job_fn = insert_job_fn

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
        payload = dict(content_payload or {})
        payload["channel"] = "wecom_customer_group"
        payload["chat_ids"] = [str(item or "").strip() for item in chat_ids if str(item or "").strip()]
        payload["sender"] = str(owner_userid or "").strip()
        if not payload["chat_ids"]:
            raise ValueError("chat_ids is required for exact WeCom customer-group queueing")
        idempotency_key = f"group_ops:{source_id or plan_id}:{scheduled_at or ''}"
        if self._insert_job_fn is not None:
            return int(self._insert_job_fn(
                source_type="workflow",
                source_table="automation_group_ops_plans",
                source_id=str(source_id or plan_id),
                idempotency_key=idempotency_key,
                business_domain="group_ops",
                channel="wecom_customer_group",
                target_kind="chat_id",
                scheduled_for=scheduled_at,
                target_external_userids=[],
                target_summary=f"{len(payload['chat_ids'])} customer groups",
                content_type="wecom_customer_group",
                content_payload=payload,
                content_summary=str(content_summary or "")[:500],
                created_by=created_by,
            ) or 0)
        db = get_db()
        row = db.execute(
            """
            INSERT INTO broadcast_jobs (
                source_type, source_id, source_table, scheduled_for, priority, batch_key,
                business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
                status, requires_approval,
                target_external_userids, target_count, target_summary,
                content_type, content_payload, content_summary,
                trace_id, created_by
            ) VALUES (
                'workflow', ?, 'automation_group_ops_plans', ?, 100, '',
                'group_ops', ?, 'wecom_customer_group', 'chat_id', '{}'::jsonb, CAST(? AS jsonb),
                'queued', FALSE,
                '[]'::jsonb, ?, ?,
                'wecom_customer_group', CAST(? AS jsonb), ?,
                ?, ?
            )
            ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> '' DO NOTHING
            RETURNING id
            """,
            (
                str(source_id or plan_id),
                scheduled_at,
                idempotency_key,
                json.dumps({"plan_id": int(plan_id), "chat_ids": payload["chat_ids"]}, ensure_ascii=False),
                len(payload["chat_ids"]),
                f"{len(payload['chat_ids'])} customer groups",
                json.dumps(payload, ensure_ascii=False),
                str(content_summary or "")[:500],
                idempotency_key,
                created_by,
            ),
        ).fetchone()
        db.commit()
        return int((row or {}).get("id") or 0)


class NextGroupOpsQueueStatsReader:
    def __init__(self, *, count_fn=None, list_jobs_fn=None) -> None:
        self._count_fn = count_fn
        self._list_jobs_fn = list_jobs_fn

    def count_group_ops_queue(self) -> int:
        if self._count_fn is not None:
            return int(self._count_fn() or 0)
        if self._list_jobs_fn is not None:
            count = 0
            for job in list(self._list_jobs_fn()):
                payload = job.get("content_payload") if isinstance(job.get("content_payload"), dict) else {}
                if job.get("source_table") == "automation_group_ops_plans" or payload.get("channel") == "wecom_customer_group":
                    count += 1
            return count
        db = get_db()
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM broadcast_jobs
            WHERE status IN ('queued', 'waiting_approval', 'claimed')
              AND source_type = 'workflow'
              AND (
                    source_table = 'automation_group_ops_plans'
                    OR business_domain = 'group_ops'
                    OR channel = 'wecom_customer_group'
                    OR content_payload->>'channel' = 'wecom_customer_group'
                  )
            """,
        ).fetchone()
        return int((row or {}).get("count") or 0)


def build_wecom_group_message_adapter() -> WeComGroupMessageAdapter:
    return WeComGroupMessageAdapter()


def build_wecom_group_asset_adapter() -> WeComGroupAssetAdapter:
    return WeComGroupAssetAdapter()


def build_wecom_group_chat_sync_adapter() -> WeComGroupAssetAdapter:
    return build_wecom_group_asset_adapter()


def build_group_ops_queue_gateway() -> NextGroupOpsQueueGateway:
    return NextGroupOpsQueueGateway()


def build_group_ops_queue_stats_gateway() -> NextGroupOpsQueueStatsReader:
    return NextGroupOpsQueueStatsReader()
