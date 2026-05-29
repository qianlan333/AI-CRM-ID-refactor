from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from typing import Any, Callable

from aicrm_next.integration_gateway.wecom_group_contract import GroupOpsQueueGatewayContract
from aicrm_next.shared.errors import ContractError

from .domain import build_node_group_message_content, clean_text, derive_node_scheduled_time
from .repo import GroupOpsRepository, build_group_ops_repository


def _parse_datetime(value: Any, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = clean_text(value).replace("Z", "+00:00")
        if not text:
            return fallback
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=fallback.tzinfo or timezone.utc)
    return parsed


def _due_at_for_group(*, plan: dict[str, Any], node: dict[str, Any], group: dict[str, Any]) -> datetime:
    fallback_start = _parse_datetime(plan.get("created_at"), fallback=datetime.now(timezone.utc))
    group_start = _parse_datetime(group.get("created_at"), fallback=fallback_start)
    scheduled_time = derive_node_scheduled_time(node)
    if not scheduled_time:
        raise ContractError("group ops node scheduled_time must use HH:MM")
    hour, minute = [int(item) for item in scheduled_time.split(":", 1)]
    day_index = max(1, int(node.get("day_index") or 1))
    due_date = group_start.date() + timedelta(days=day_index - 1)
    return datetime.combine(due_date, time(hour=hour, minute=minute), tzinfo=group_start.tzinfo)


def _minute_key(value: datetime) -> str:
    return value.replace(second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y%m%dT%H%MZ")


def _stable_hash(value: Any, *, length: int = 12) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:length]


def _content_hash(payload: dict[str, Any]) -> str:
    payload_for_hash = dict(payload or {})
    payload_for_hash.pop("chat_ids", None)
    return _stable_hash(payload_for_hash, length=16)


def _default_duplicate_checker(idempotency_key: str) -> bool:
    if not idempotency_key:
        return False
    from wecom_ability_service.domains.broadcast_jobs import repo as broadcast_queue_repo

    return bool(broadcast_queue_repo.fetch_job_by_idempotency_key(idempotency_key))


@dataclass
class GroupOpsSchedulerSummary:
    scanned_at: str
    group_ops_scanned_plans: int = 0
    group_ops_due_nodes: int = 0
    group_ops_enqueued_jobs: int = 0
    group_ops_skipped_future: int = 0
    group_ops_skipped_duplicate: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "group_ops_scanned_plans": self.group_ops_scanned_plans,
            "group_ops_due_nodes": self.group_ops_due_nodes,
            "group_ops_enqueued_jobs": self.group_ops_enqueued_jobs,
            "group_ops_skipped_future": self.group_ops_skipped_future,
            "group_ops_skipped_duplicate": self.group_ops_skipped_duplicate,
            "errors": self.errors,
        }


class GroupOpsDueScheduler:
    def __init__(
        self,
        *,
        repo: GroupOpsRepository | None = None,
        queue_gateway: GroupOpsQueueGatewayContract | None = None,
        duplicate_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self._repo = repo
        self._queue_gateway = queue_gateway
        self._duplicate_checker = duplicate_checker or _default_duplicate_checker

    def run_due(self, *, now: datetime | None = None, operator: str = "automation_ops_scheduler") -> dict[str, Any]:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        summary = GroupOpsSchedulerSummary(scanned_at=current_time.isoformat())
        repo = self._repo or build_group_ops_repository()
        if repo is None:
            summary.errors.append({"scope": "group_ops", "error": "group ops repository unavailable"})
            return summary.as_dict()
        if self._queue_gateway is None:
            from aicrm_next.integration_gateway.wecom_group_adapter import build_group_ops_queue_gateway

            queue_gateway = build_group_ops_queue_gateway()
        else:
            queue_gateway = self._queue_gateway

        plans, _total = repo.list_plans({"plan_type": "standard", "status": "active", "limit": 500, "offset": 0})
        for plan in plans:
            summary.group_ops_scanned_plans += 1
            plan_id = int(plan.get("id") or 0)
            try:
                groups = [
                    group
                    for group in repo.list_bound_groups(plan_id)
                    if clean_text(group.get("status") or "active") == "active" and clean_text(group.get("chat_id"))
                ]
                if not groups:
                    continue
                nodes = [
                    node
                    for node in repo.list_nodes(plan_id)
                    if clean_text(node.get("status") or "active") == "active"
                ]
                for node in nodes:
                    self._schedule_node(
                        summary=summary,
                        queue_gateway=queue_gateway,
                        plan=plan,
                        node=node,
                        groups=groups,
                        now=current_time,
                        operator=operator,
                    )
            except Exception as exc:
                summary.errors.append({"scope": "group_ops_plan", "plan_id": plan_id, "error": str(exc)})
        return summary.as_dict()

    def _schedule_node(
        self,
        *,
        summary: GroupOpsSchedulerSummary,
        queue_gateway: GroupOpsQueueGatewayContract,
        plan: dict[str, Any],
        node: dict[str, Any],
        groups: list[dict[str, Any]],
        now: datetime,
        operator: str,
    ) -> None:
        content = build_node_group_message_content(node=node, sender=clean_text(plan.get("owner_userid")))
        base_payload = dict(content)
        base_payload.setdefault("attachments", [])
        base_payload["channel"] = "wecom_customer_group"
        base_payload["sender"] = clean_text(plan.get("owner_userid"))
        base_payload["plan_id"] = int(plan.get("id") or 0)
        base_payload["node_id"] = int(node.get("id") or 0)
        content_hash = _content_hash(base_payload)
        due_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        for group in groups:
            due_at = _due_at_for_group(plan=plan, node=node, group=group)
            if due_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                summary.group_ops_skipped_future += 1
                continue
            summary.group_ops_due_nodes += 1
            key = (
                due_at.isoformat(timespec="minutes"),
                clean_text(plan.get("owner_userid")),
                content_hash,
            )
            bucket = due_groups.setdefault(key, {"due_at": due_at, "chat_ids": []})
            bucket["chat_ids"].append(clean_text(group.get("chat_id")))

        for bucket in due_groups.values():
            chat_ids = sorted(dict.fromkeys(bucket["chat_ids"]))
            due_at = bucket["due_at"]
            chat_hash = _stable_hash(chat_ids)
            source_id = f"{int(plan['id'])}:node:{int(node['id'])}:due:{_minute_key(due_at)}:groups:{chat_hash}"
            idempotency_key = f"group_ops:{source_id}:{due_at.isoformat(timespec='minutes')}"
            if self._duplicate_checker(idempotency_key):
                summary.group_ops_skipped_duplicate += 1
                continue
            content_payload = dict(base_payload)
            content_payload["chat_ids"] = chat_ids
            job_id = queue_gateway.enqueue_group_message(
                plan_id=int(plan["id"]),
                source_id=source_id,
                scheduled_at=due_at.isoformat(timespec="minutes"),
                owner_userid=clean_text(plan.get("owner_userid")),
                chat_ids=chat_ids,
                content_payload=content_payload,
                content_summary=(content.get("text") or {}).get("content", "") or clean_text(node.get("action_title")),
                created_by=clean_text(operator) or "automation_ops_scheduler",
            )
            if int(job_id or 0):
                summary.group_ops_enqueued_jobs += 1


def run_group_ops_due_scheduler(
    *,
    repo: GroupOpsRepository | None = None,
    queue_gateway: GroupOpsQueueGatewayContract | None = None,
    duplicate_checker: Callable[[str], bool] | None = None,
    now: datetime | None = None,
    operator: str = "automation_ops_scheduler",
) -> dict[str, Any]:
    return GroupOpsDueScheduler(
        repo=repo,
        queue_gateway=queue_gateway,
        duplicate_checker=duplicate_checker,
    ).run_due(now=now, operator=operator)
