from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Protocol

from sqlalchemy import create_engine

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url

from .domain import (
    binding_stats,
    clean_text,
    generate_webhook_key,
    generate_webhook_token,
    hash_webhook_token,
    normalize_plan_payload,
    utc_now_iso,
)

GROUP_OPS_BACKEND_ENV = "AICRM_GROUP_OPS_REPO_BACKEND"
GROUP_OPS_DATABASE_URL_ENV = "AICRM_GROUP_OPS_DATABASE_URL"
GROUP_OPS_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}


class GroupOpsRepository(Protocol):
    def list_plans(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]: ...
    def get_plan(self, plan_id: int) -> dict[str, Any] | None: ...
    def get_plan_by_webhook_key(self, webhook_key: str) -> dict[str, Any] | None: ...
    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_plan(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def list_bound_groups(self, plan_id: int) -> list[dict[str, Any]]: ...
    def bind_group(self, plan_id: int, group: dict[str, Any]) -> dict[str, Any]: ...
    def remove_group(self, plan_id: int, chat_id: str) -> bool: ...
    def list_group_assets(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]: ...
    def get_group_asset(self, chat_id: str) -> dict[str, Any] | None: ...
    def upsert_group_snapshots(self, groups: list[dict[str, Any]]) -> int: ...
    def list_owners(self) -> list[dict[str, Any]]: ...
    def list_nodes(self, plan_id: int) -> list[dict[str, Any]]: ...
    def create_node(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_node(self, plan_id: int, node_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def delete_node(self, plan_id: int, node_id: int) -> bool: ...
    def regenerate_webhook(self, plan_id: int) -> dict[str, Any]: ...
    def find_webhook_event(self, plan_id: int, idempotency_key: str) -> dict[str, Any] | None: ...
    def create_webhook_event(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_webhook_event(self, event_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...


def _fixture_groups() -> dict[str, dict[str, Any]]:
    return {
        "wrOgAAA001": {
            "chat_id": "wrOgAAA001",
            "group_name": "体验课 01 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "internal_member_count": 12,
            "external_member_count": 150,
            "synced_at": "2026-05-25T08:00:00Z",
            "status": "active",
        },
        "wrOgAAA002": {
            "chat_id": "wrOgAAA002",
            "group_name": "体验课 02 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "internal_member_count": 10,
            "external_member_count": 160,
            "synced_at": "2026-05-25T08:00:00Z",
            "status": "active",
        },
        "wrOgAAA003": {
            "chat_id": "wrOgAAA003",
            "group_name": "体验课 03 群",
            "owner_userid": "owner_001",
            "owner_name": "王小明",
            "internal_member_count": 9,
            "external_member_count": 176,
            "synced_at": "2026-05-25T08:00:00Z",
            "status": "active",
        },
        "wrOgBBB001": {
            "chat_id": "wrOgBBB001",
            "group_name": "成交陪跑 01 群",
            "owner_userid": "owner_002",
            "owner_name": "李小红",
            "internal_member_count": 8,
            "external_member_count": 88,
            "synced_at": "2026-05-25T08:00:00Z",
            "status": "active",
        },
    }


class InMemoryGroupOpsRepository:
    source_status = "fixture_local_contract"

    def __init__(self, *, seed_groups: bool = True) -> None:
        now = utc_now_iso()
        token = "fixture-webhook-token"
        self._plans: dict[int, dict[str, Any]] = {
            1: {
                "id": 1,
                "plan_code": "group_plan_001",
                "plan_name": "体验课 7 日群运营",
                "plan_type": "standard",
                "owner_userid": "owner_001",
                "owner_name": "王小明",
                "status": "active",
                "webhook_key": "",
                "webhook_token_hash": "",
                "created_by": "fixture",
                "updated_by": "fixture",
                "created_at": now,
                "updated_at": now,
                "archived_at": "",
            },
            2: {
                "id": 2,
                "plan_code": "group_webhook_001",
                "plan_name": "每日课程 Webhook 群运营",
                "plan_type": "webhook",
                "owner_userid": "owner_001",
                "owner_name": "王小明",
                "status": "active",
                "webhook_key": "daily-lesson-8f3a",
                "webhook_token_hash": hash_webhook_token(token),
                "created_by": "fixture",
                "updated_by": "fixture",
                "created_at": now,
                "updated_at": now,
                "archived_at": "",
            },
            3: {
                "id": 3,
                "plan_code": "group_plan_002",
                "plan_name": "成交陪跑 3 日群运营",
                "plan_type": "standard",
                "owner_userid": "owner_002",
                "owner_name": "李小红",
                "status": "draft",
                "webhook_key": "",
                "webhook_token_hash": "",
                "created_by": "fixture",
                "updated_by": "fixture",
                "created_at": now,
                "updated_at": now,
                "archived_at": "",
            },
        }
        self._groups = _fixture_groups() if seed_groups else {}
        self._next_plan_group_id = 1
        self._plan_groups: dict[int, dict[str, dict[str, Any]]] = {1: {}, 2: {}}
        if seed_groups:
            self._plan_groups = {
                1: {
                    "wrOgAAA001": self._snapshot_group(1, self._groups["wrOgAAA001"]),
                    "wrOgAAA002": self._snapshot_group(1, self._groups["wrOgAAA002"]),
                },
                2: {
                    "wrOgAAA001": self._snapshot_group(2, self._groups["wrOgAAA001"]),
                },
            }
        self._nodes: dict[int, dict[int, dict[str, Any]]] = {
            1: {
                1: {
                    "id": 1,
                    "plan_id": 1,
                    "day_index": 1,
                    "trigger_time_label": "入群后 10 分钟",
                    "action_title": "欢迎语 + 课程入口",
                    "text_content": "欢迎加入体验课群。",
                    "attachments": [],
                    "sort_order": 10,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            }
        }
        self._webhook_events: dict[int, dict[str, Any]] = {}
        self._next_plan_id = 4
        self._next_node_id = 2
        self._next_event_id = 1

    def _snapshot_group(self, plan_id: int, group: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        row = {
            "id": self._next_plan_group_id,
            "plan_id": int(plan_id),
            "chat_id": group["chat_id"],
            "group_name_snapshot": group["group_name"],
            "owner_userid_snapshot": group["owner_userid"],
            "internal_member_count_snapshot": int(group.get("internal_member_count") or 0),
            "external_member_count_snapshot": int(group.get("external_member_count") or 0),
            "status": "active",
            "created_at": now,
            "removed_at": "",
        }
        self._next_plan_group_id += 1
        return row

    def list_plans(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        keyword = clean_text(filters.get("keyword")).lower()
        plan_type = clean_text(filters.get("plan_type")).lower()
        status = clean_text(filters.get("status")).lower()
        rows = []
        for plan in self._plans.values():
            if plan.get("archived_at"):
                continue
            haystack = f"{plan.get('plan_name')} {plan.get('plan_code')} {plan.get('owner_userid')}".lower()
            if keyword and keyword not in haystack:
                continue
            if plan_type and plan.get("plan_type") != plan_type:
                continue
            if status and plan.get("status") != status:
                continue
            rows.append(deepcopy(plan))
        rows.sort(key=lambda item: int(item["id"]))
        offset = max(0, int(filters.get("offset") or 0))
        limit = max(1, int(filters.get("limit") or 50))
        return rows[offset : offset + limit], len(rows)

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        plan = self._plans.get(int(plan_id))
        return deepcopy(plan) if plan and not plan.get("archived_at") else None

    def get_plan_by_webhook_key(self, webhook_key: str) -> dict[str, Any] | None:
        key = clean_text(webhook_key)
        for plan in self._plans.values():
            if plan.get("webhook_key") == key and not plan.get("archived_at"):
                return deepcopy(plan)
        return None

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_plan_payload(payload)
        plan_id = self._next_plan_id
        self._next_plan_id += 1
        now = utc_now_iso()
        plan_code = normalized["plan_code"] or f"group_plan_{plan_id:03d}"
        webhook_key = ""
        webhook_token_hash = ""
        if normalized["plan_type"] == "webhook":
            webhook_key = generate_webhook_key(normalized["plan_name"])
            webhook_token_hash = hash_webhook_token(generate_webhook_token())
        row = {
            "id": plan_id,
            **normalized,
            "plan_code": plan_code,
            "owner_name": "",
            "webhook_key": webhook_key,
            "webhook_token_hash": webhook_token_hash,
            "created_at": now,
            "updated_at": now,
            "archived_at": "",
        }
        self._plans[plan_id] = row
        self._plan_groups.setdefault(plan_id, {})
        self._nodes.setdefault(plan_id, {})
        return deepcopy(row)

    def update_plan(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._plans.get(int(plan_id))
        if not current:
            raise NotFoundError("group ops plan not found")
        normalized = normalize_plan_payload(payload, existing=current)
        current.update(normalized)
        current["plan_code"] = normalized["plan_code"] or current["plan_code"]
        current["updated_at"] = utc_now_iso()
        return deepcopy(current)

    def list_bound_groups(self, plan_id: int) -> list[dict[str, Any]]:
        rows = list(self._plan_groups.get(int(plan_id), {}).values())
        return [deepcopy(item) for item in rows if item.get("status") == "active"]

    def bind_group(self, plan_id: int, group: dict[str, Any]) -> dict[str, Any]:
        self._plan_groups.setdefault(int(plan_id), {})
        existing = self._plan_groups[int(plan_id)].get(group["chat_id"])
        if existing:
            existing["status"] = "active"
            existing["removed_at"] = ""
            return deepcopy(existing)
        row = self._snapshot_group(int(plan_id), group)
        self._plan_groups[int(plan_id)][group["chat_id"]] = row
        return deepcopy(row)

    def remove_group(self, plan_id: int, chat_id: str) -> bool:
        item = self._plan_groups.get(int(plan_id), {}).get(clean_text(chat_id))
        if not item or item.get("status") != "active":
            return False
        item["status"] = "removed"
        item["removed_at"] = utc_now_iso()
        return True

    def list_group_assets(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        keyword = clean_text(filters.get("keyword")).lower()
        owner_userid = clean_text(filters.get("owner_userid"))
        plan_id = int(filters.get("plan_id") or 0)
        bind_status = clean_text(filters.get("bind_status")).lower()
        rows = []
        for group in self._groups.values():
            if keyword and keyword not in f"{group.get('group_name')} {group.get('chat_id')}".lower():
                continue
            if owner_userid and group.get("owner_userid") != owner_userid:
                continue
            bound_plan = self._bound_plan_for_group(group["chat_id"], plan_id=plan_id)
            is_bound = bool(bound_plan)
            if bind_status == "bound" and not is_bound:
                continue
            if bind_status == "unbound" and is_bound:
                continue
            row = deepcopy(group)
            row["bound_plan_id"] = int(bound_plan.get("id") or 0) if bound_plan else 0
            row["plan_name"] = clean_text(bound_plan.get("plan_name")) if bound_plan else ""
            row["bind_status"] = "bound" if is_bound else "unbound"
            rows.append(row)
        offset = max(0, int(filters.get("offset") or 0))
        limit = max(1, int(filters.get("limit") or 50))
        return rows[offset : offset + limit], len(rows)

    def _bound_plan_for_group(self, chat_id: str, *, plan_id: int = 0) -> dict[str, Any] | None:
        for current_plan_id, groups in self._plan_groups.items():
            if plan_id and current_plan_id != plan_id:
                continue
            binding = groups.get(chat_id)
            if binding and binding.get("status") == "active":
                return self._plans.get(current_plan_id)
        return None

    def get_group_asset(self, chat_id: str) -> dict[str, Any] | None:
        group = self._groups.get(clean_text(chat_id))
        return deepcopy(group) if group else None

    def upsert_group_snapshots(self, groups: list[dict[str, Any]]) -> int:
        count = 0
        for group in groups:
            chat_id = clean_text(group.get("chat_id"))
            if not chat_id:
                continue
            self._groups[chat_id] = {
                "chat_id": chat_id,
                "group_name": clean_text(group.get("group_name") or chat_id),
                "owner_userid": clean_text(group.get("owner_userid")),
                "owner_name": clean_text(group.get("owner_name") or group.get("owner_userid")),
                "internal_member_count": int(group.get("internal_member_count") or 0),
                "external_member_count": int(group.get("external_member_count") or 0),
                "synced_at": utc_now_iso(),
                "status": clean_text(group.get("status") or "active"),
            }
            count += 1
        return count

    def list_owners(self) -> list[dict[str, Any]]:
        owners: dict[str, dict[str, Any]] = {}
        for group in self._groups.values():
            userid = clean_text(group.get("owner_userid"))
            if not userid:
                continue
            current = owners.setdefault(userid, {"userid": userid, "name": clean_text(group.get("owner_name")) or userid, "group_count": 0})
            current["group_count"] += 1
            if group.get("owner_name"):
                current["name"] = clean_text(group.get("owner_name"))
        for plan in self._plans.values():
            userid = clean_text(plan.get("owner_userid"))
            if userid and userid not in owners:
                owners[userid] = {"userid": userid, "name": clean_text(plan.get("owner_name")) or userid, "group_count": 0}
        return [deepcopy(item) for item in sorted(owners.values(), key=lambda item: item["userid"])]

    def list_nodes(self, plan_id: int) -> list[dict[str, Any]]:
        rows = list(self._nodes.get(int(plan_id), {}).values())
        rows = [item for item in rows if item.get("status") != "deleted"]
        rows.sort(key=lambda item: (int(item.get("day_index") or 0), int(item.get("sort_order") or 0), int(item["id"])))
        return deepcopy(rows)

    def create_node(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        node_id = self._next_node_id
        self._next_node_id += 1
        row = {
            "id": node_id,
            "plan_id": int(plan_id),
            **payload,
            "created_at": now,
            "updated_at": now,
        }
        self._nodes.setdefault(int(plan_id), {})[node_id] = row
        return deepcopy(row)

    def update_node(self, plan_id: int, node_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._nodes.get(int(plan_id), {}).get(int(node_id))
        if not current:
            raise NotFoundError("group ops node not found")
        current.update(payload)
        current["updated_at"] = utc_now_iso()
        return deepcopy(current)

    def delete_node(self, plan_id: int, node_id: int) -> bool:
        current = self._nodes.get(int(plan_id), {}).get(int(node_id))
        if not current:
            return False
        current["status"] = "deleted"
        current["updated_at"] = utc_now_iso()
        return True

    def regenerate_webhook(self, plan_id: int) -> dict[str, Any]:
        plan = self._plans.get(int(plan_id))
        if not plan:
            raise NotFoundError("group ops plan not found")
        plaintext_token = generate_webhook_token()
        plan["webhook_key"] = plan.get("webhook_key") or generate_webhook_key(plan["plan_name"])
        plan["webhook_token_hash"] = hash_webhook_token(plaintext_token)
        plan["updated_at"] = utc_now_iso()
        result = deepcopy(plan)
        result["plaintext_token"] = plaintext_token
        return result

    def find_webhook_event(self, plan_id: int, idempotency_key: str) -> dict[str, Any] | None:
        key = clean_text(idempotency_key)
        for event in self._webhook_events.values():
            if int(event.get("plan_id") or 0) == int(plan_id) and event.get("idempotency_key") == key:
                return deepcopy(event)
        return None

    def create_webhook_event(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = self._next_event_id
        self._next_event_id += 1
        row = {
            "id": event_id,
            "plan_id": int(plan_id),
            "idempotency_key": clean_text(payload.get("idempotency_key")),
            "request_payload": deepcopy(payload.get("request_payload") or {}),
            "normalized_content_payload": deepcopy(payload.get("normalized_content_payload") or {}),
            "scheduled_at": clean_text(payload.get("scheduled_at")),
            "status": clean_text(payload.get("status") or "accepted"),
            "broadcast_job_ids": list(payload.get("broadcast_job_ids") or []),
            "error_message": clean_text(payload.get("error_message")),
            "created_at": utc_now_iso(),
        }
        self._webhook_events[event_id] = row
        return deepcopy(row)

    def update_webhook_event(self, event_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._webhook_events.get(int(event_id))
        if not current:
            raise NotFoundError("group ops webhook event not found")
        current.update(deepcopy(payload))
        return deepcopy(current)


_fixture_repo = InMemoryGroupOpsRepository()


def build_group_ops_repository() -> GroupOpsRepository:
    backend = clean_text(os.getenv(GROUP_OPS_BACKEND_ENV)).lower()
    if production_data_ready() or backend in GROUP_OPS_SQL_BACKENDS:
        database_url = clean_text(os.getenv(GROUP_OPS_DATABASE_URL_ENV)) or raw_database_url()
        if not database_url:
            raise ContractError(f"{GROUP_OPS_DATABASE_URL_ENV} or DATABASE_URL is required for group ops Postgres repository")
        from .postgres_repo import PostgresGroupOpsRepository

        return assert_repository_allowed(
            PostgresGroupOpsRepository(create_engine(_sqlalchemy_database_url(database_url), future=True)),
            capability_owner="aicrm_next.automation_engine.group_ops",
        )
    return assert_repository_allowed(_fixture_repo, capability_owner="aicrm_next.automation_engine.group_ops")


def _sqlalchemy_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def reset_group_ops_fixture_state(*, seed_groups: bool = True) -> None:
    global _fixture_repo
    _fixture_repo = InMemoryGroupOpsRepository(seed_groups=seed_groups)


def plan_binding_summary(repo: GroupOpsRepository, plan_id: int) -> dict[str, int]:
    return binding_stats(repo.list_bound_groups(int(plan_id)))
