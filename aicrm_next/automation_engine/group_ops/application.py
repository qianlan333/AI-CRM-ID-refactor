from __future__ import annotations

import os
from typing import Any

from aicrm_next.integration_gateway.wecom_group_contract import GroupOpsQueueGatewayContract, WeComGroupAssetAdapterContract
from aicrm_next.shared.errors import ApplicationError, ContractError, NotFoundError
from aicrm_next.shared.repository_provider import blocked_production_payload

from . import CAPABILITY_OWNER
from .domain import (
    assert_group_owned_by_plan,
    assert_run_due_guard,
    build_node_group_message_content,
    binding_stats,
    clean_text,
    clamp_limit,
    extract_bearer_token,
    normalize_message_content,
    normalize_group_snapshots,
    normalize_node_payload,
    verify_webhook_token,
)
from .dto import (
    GroupOpsBindGroupRequest,
    GroupOpsGroupSyncRequest,
    GroupOpsGroupsRequest,
    GroupOpsNodeRequest,
    GroupOpsPlanCreateRequest,
    GroupOpsPlanListRequest,
    GroupOpsRunDueRequest,
    GroupOpsPlanUpdateRequest,
    GroupOpsWebhookReceiveRequest,
)
from .projections import group_asset_item, plan_list_item
from .repo import GroupOpsRepository, build_group_ops_repository, plan_binding_summary


class UnauthorizedError(ApplicationError):
    status_code = 401


class ConflictError(ApplicationError):
    status_code = 409


def group_ops_side_effect_safety(**overrides: bool) -> dict[str, bool]:
    safety = {
        "real_wecom_call_executed": False,
        "real_outbound_send_executed": False,
        "real_external_call_executed": False,
        "real_timer_executed": False,
        "real_queue_worker_created": False,
        "real_group_notice_executed": False,
        "real_mention_all_executed": False,
        "db_write_executed": False,
        "outbound_send_executed": False,
        "no_db_write": True,
        "no_outbound_send": True,
    }
    safety.update({key: bool(value) for key, value in overrides.items() if key in safety})
    return safety


def _response(payload: dict[str, Any], *, status_code: int = 200, repo: GroupOpsRepository | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": str(getattr(repo, "source_status", "fixture_local_contract")),
        "route_owner": "ai_crm_next",
        "capability_owner": CAPABILITY_OWNER,
        "status_code": status_code,
        "side_effect_safety": group_ops_side_effect_safety(),
        **payload,
    }


def _production_unavailable() -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner=CAPABILITY_OWNER,
        detail="group ops production repository is not enabled; real WeCom group outbound remains disabled.",
    )
    payload.update(
        {
            "status_code": 503,
            "route_owner": "ai_crm_next",
            "side_effect_safety": group_ops_side_effect_safety(),
        }
    )
    return payload


def _repo_or_block(repo: GroupOpsRepository | None) -> GroupOpsRepository | None:
    return repo or build_group_ops_repository()


def _public_base_url() -> str:
    for key in ("AICRM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL", "EXTERNAL_BASE_URL"):
        value = str(os.getenv(key, "") or "").strip().rstrip("/")
        if value:
            return value
    return "https://www.youcangogogo.com"


def _queue_count() -> int:
    try:
        from aicrm_next.integration_gateway.wecom_group_adapter import build_group_ops_queue_stats_gateway

        return int(build_group_ops_queue_stats_gateway().count_group_ops_queue())
    except Exception:
        return 0


def _plan_or_404(repo: GroupOpsRepository, plan_id: int) -> dict[str, Any]:
    plan = repo.get_plan(int(plan_id))
    if not plan:
        raise NotFoundError("group ops plan not found")
    return plan


class ListGroupOpsPlansQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, request: GroupOpsPlanListRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        rows, total = repo.list_plans(
            {
                "keyword": request.keyword,
                "plan_type": request.plan_type,
                "status": request.status,
                "limit": clamp_limit(request.limit),
                "offset": max(0, int(request.offset or 0)),
            }
        )
        items = [
            plan_list_item(plan, groups=repo.list_bound_groups(int(plan["id"])), owner_name=clean_text(plan.get("owner_name")))
            for plan in rows
        ]
        return _response({"items": items, "total": total, "queue_count": _queue_count()}, repo=repo)


class ListGroupOpsOwnersQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        owners = [
            {
                "userid": clean_text(item.get("userid")),
                "name": clean_text(item.get("name") or item.get("userid")),
                "group_count": int(item.get("group_count") or 0),
            }
            for item in repo.list_owners()
            if clean_text(item.get("userid"))
        ]
        return _response({"items": owners, "total": len(owners)}, repo=repo)


class CreateGroupOpsPlanCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, request: GroupOpsPlanCreateRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = repo.create_plan(request.model_dump())
        return _response({"item": plan}, status_code=201, repo=repo)


class GetGroupOpsPlanQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = _plan_or_404(repo, plan_id)
        return _response(
            {
                "item": plan,
                "groups_summary": plan_binding_summary(repo, int(plan_id)),
                "nodes": repo.list_nodes(int(plan_id)),
            },
            repo=repo,
        )


class UpdateGroupOpsPlanCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, request: GroupOpsPlanUpdateRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        plan = repo.update_plan(int(plan_id), request.model_dump(exclude_none=True))
        return _response({"item": plan}, repo=repo)


class ListGroupOpsPlanGroupsQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        groups = repo.list_bound_groups(int(plan_id))
        return _response({"items": groups, "summary": binding_stats(groups), "total": len(groups)}, repo=repo)


class AddGroupOpsPlanGroupCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, request: GroupOpsBindGroupRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = _plan_or_404(repo, plan_id)
        group = repo.get_group_asset(request.chat_id)
        if not group:
            raise NotFoundError("group chat snapshot not found")
        assert_group_owned_by_plan(group=group, plan=plan)
        item = repo.bind_group(int(plan_id), group)
        groups = repo.list_bound_groups(int(plan_id))
        return _response({"item": item, "summary": binding_stats(groups)}, status_code=201, repo=repo)


class RemoveGroupOpsPlanGroupCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, chat_id: str) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        removed = repo.remove_group(int(plan_id), chat_id)
        if not removed:
            raise NotFoundError("group binding not found")
        return _response({"removed": True, "summary": binding_stats(repo.list_bound_groups(int(plan_id)))}, repo=repo)


class ListGroupOpsNodesQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        items = repo.list_nodes(int(plan_id))
        return _response({"items": items, "total": len(items)}, repo=repo)


class CreateGroupOpsNodeCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, request: GroupOpsNodeRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        item = repo.create_node(int(plan_id), normalize_node_payload(request.model_dump()))
        return _response({"item": item}, status_code=201, repo=repo)


class UpdateGroupOpsNodeCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, node_id: int, request: GroupOpsNodeRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        existing = next((item for item in repo.list_nodes(int(plan_id)) if int(item["id"]) == int(node_id)), None)
        if not existing:
            raise NotFoundError("group ops node not found")
        item = repo.update_node(int(plan_id), int(node_id), normalize_node_payload(request.model_dump(), existing=existing))
        return _response({"item": item}, repo=repo)


class DeleteGroupOpsNodeCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, node_id: int) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        _plan_or_404(repo, plan_id)
        if not repo.delete_node(int(plan_id), int(node_id)):
            raise NotFoundError("group ops node not found")
        return _response({"deleted": True}, repo=repo)


class ListGroupOpsGroupsQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, request: GroupOpsGroupsRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        rows, total = repo.list_group_assets(
            {
                "keyword": request.keyword,
                "owner_userid": request.owner_userid,
                "plan_id": request.plan_id or 0,
                "bind_status": request.bind_status,
                "limit": clamp_limit(request.limit),
                "offset": max(0, int(request.offset or 0)),
            }
        )
        items = [
            group_asset_item(row, plan_name=clean_text(row.get("plan_name")), bind_status=clean_text(row.get("bind_status") or "unbound"))
            for row in rows
        ]
        return _response({"items": items, "total": total}, repo=repo)


def _group_sync_adapter() -> WeComGroupAssetAdapterContract:
    from aicrm_next.integration_gateway.wecom_group_adapter import build_wecom_group_asset_adapter

    return build_wecom_group_asset_adapter()


def _group_sync_blocked_response(
    *,
    owner_userid: str,
    result: dict[str, Any],
    repo: GroupOpsRepository,
) -> dict[str, Any]:
    mode = clean_text(result.get("mode"))
    error_code = clean_text(result.get("error_code") or "wecom_group_sync_blocked")
    status = "disabled" if mode in {"disabled", "staging"} or "disabled" in error_code else "blocked"
    return {
        "ok": False,
        "source_status": str(getattr(repo, "source_status", "fixture_local_contract")),
        "route_owner": "ai_crm_next",
        "capability_owner": CAPABILITY_OWNER,
        "status_code": 409,
        "owner_userid": owner_userid,
        "status": status,
        "sync_status": status,
        "adapter_mode": mode,
        "synced_count": 0,
        "new_count": 0,
        "updated_count": 0,
        "skipped_count": int(result.get("skipped_count") or 0),
        "next_cursor": "",
        "items": [],
        "warnings": [clean_text(result.get("error_message")) or "wecom group sync blocked"],
        "error_code": error_code,
        "error_message": clean_text(result.get("error_message")) or "wecom group sync blocked",
        "side_effect_safety": group_ops_side_effect_safety(),
    }


class PreviewGroupOpsOwnerGroupsSyncCommand:
    def __init__(self, repo: GroupOpsRepository | None = None, sync_adapter: WeComGroupAssetAdapterContract | None = None) -> None:
        self._repo = repo
        self._sync_adapter = sync_adapter

    def __call__(self, request: GroupOpsGroupSyncRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        owner = clean_text(request.owner_userid)
        if not owner:
            raise ContractError("owner_userid is required")
        adapter = self._sync_adapter or _group_sync_adapter()
        result = adapter.list_group_chats(owner_userid=owner, limit=clamp_limit(request.limit, default=100), cursor=request.cursor)
        if not result.get("ok"):
            return _group_sync_blocked_response(owner_userid=owner, result=result, repo=repo)
        groups = normalize_group_snapshots(list(result.get("groups") or []))
        return _response(
            {
                "owner_userid": owner,
                "status": "preview",
                "sync_status": "preview",
                "adapter_mode": clean_text(result.get("mode")),
                "items": groups,
                "total": len(groups),
                "synced_count": 0,
                "new_count": 0,
                "updated_count": 0,
                "skipped_count": int(result.get("skipped_count") or 0),
                "next_cursor": clean_text(result.get("next_cursor")),
                "warnings": [clean_text(item) for item in list(result.get("warnings") or []) if clean_text(item)],
                "side_effect_safety": group_ops_side_effect_safety(),
            },
            repo=repo,
        )


class SyncGroupOpsOwnerGroupsCommand(PreviewGroupOpsOwnerGroupsSyncCommand):
    def __call__(self, request: GroupOpsGroupSyncRequest) -> dict[str, Any]:
        preview = super().__call__(request)
        if preview.get("ok") is False:
            return preview
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        groups = list(preview.get("items") or [])
        saved_items: list[dict[str, Any]] = []
        new_count = 0
        updated_count = 0
        skipped_count = int(preview.get("skipped_count") or 0)
        warnings = list(preview.get("warnings") or [])
        for group in groups:
            try:
                saved, action = repo.upsert_group_asset(group)
            except Exception as exc:
                skipped_count += 1
                warnings.append(str(exc))
                continue
            saved_items.append(saved)
            if action == "created":
                new_count += 1
            elif action == "updated":
                updated_count += 1
        return _response(
            {
                "owner_userid": clean_text(preview.get("owner_userid") or request.owner_userid),
                "status": "synced",
                "sync_status": "synced",
                "adapter_mode": clean_text(preview.get("adapter_mode")),
                "items": saved_items,
                "total": len(saved_items),
                "synced_count": len(saved_items),
                "new_count": new_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "next_cursor": clean_text(preview.get("next_cursor")),
                "warnings": warnings,
                "side_effect_safety": group_ops_side_effect_safety(
                    db_write_executed=bool(saved_items),
                    no_db_write=False,
                    no_outbound_send=True,
                ),
            },
            repo=repo,
        )


PreviewGroupOpsGroupsSyncCommand = PreviewGroupOpsOwnerGroupsSyncCommand
SyncGroupOpsGroupsCommand = SyncGroupOpsOwnerGroupsCommand


def _run_due_candidates(
    *,
    repo: GroupOpsRepository,
    plan: dict[str, Any],
    allow_plan_ids: list[int] | None = None,
    allow_node_ids: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    if plan.get("plan_type") != "standard":
        raise ContractError("run-due is only available for standard group ops plans")
    if plan.get("status") != "active":
        raise ConflictError("group ops plan is not active")
    groups = repo.list_bound_groups(int(plan["id"]))
    if not groups:
        raise ConflictError("standard plan has no bound groups")
    nodes = [item for item in repo.list_nodes(int(plan["id"])) if clean_text(item.get("status") or "active") == "active"]
    allowed_plans = {int(item) for item in allow_plan_ids or []}
    allowed_nodes = {int(item) for item in allow_node_ids or []}
    if allowed_nodes and int(plan["id"]) not in allowed_plans:
        nodes = [item for item in nodes if int(item.get("id") or 0) in allowed_nodes]
    stats = binding_stats(groups)
    chat_ids = [clean_text(item.get("chat_id")) for item in groups if clean_text(item.get("chat_id"))]
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        content = build_node_group_message_content(node=node, sender=clean_text(plan.get("owner_userid")))
        content_payload = dict(content)
        content_payload["channel"] = "wecom_customer_group"
        content_payload["sender"] = clean_text(plan.get("owner_userid"))
        content_payload["chat_ids"] = chat_ids
        candidates.append(
            {
                "plan_id": int(plan["id"]),
                "node_id": int(node["id"]),
                "day_index": int(node.get("day_index") or 0),
                "trigger_time_label": clean_text(node.get("trigger_time_label")),
                "action_title": clean_text(node.get("action_title")),
                "chat_ids": chat_ids,
                "group_count": len(chat_ids),
                "estimated_reach": int(stats["estimated_reach"]),
                "content_payload": content_payload,
                "content_summary": (content.get("text") or {}).get("content", "") or clean_text(node.get("action_title")),
            }
        )
    return candidates, groups, stats


class PreviewGroupOpsPlanRunDueCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int, request: GroupOpsRunDueRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = _plan_or_404(repo, plan_id)
        candidates, groups, stats = _run_due_candidates(
            repo=repo,
            plan=plan,
            allow_plan_ids=request.allow_plan_ids,
            allow_node_ids=request.allow_node_ids,
        )
        if request.max_outbound_tasks:
            candidates = candidates[: max(0, int(request.max_outbound_tasks))]
        return _response(
            {
                "status": "preview",
                "plan_id": int(plan_id),
                "items": candidates,
                "groups": groups,
                "summary": stats,
                "total": len(candidates),
            },
            repo=repo,
        )


class RunGroupOpsPlanDueCommand:
    def __init__(
        self,
        repo: GroupOpsRepository | None = None,
        queue_gateway: GroupOpsQueueGatewayContract | None = None,
    ) -> None:
        self._repo = repo
        self._queue_gateway = queue_gateway

    def __call__(self, plan_id: int, request: GroupOpsRunDueRequest) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = _plan_or_404(repo, plan_id)
        candidates, groups, stats = _run_due_candidates(
            repo=repo,
            plan=plan,
            allow_plan_ids=request.allow_plan_ids,
            allow_node_ids=request.allow_node_ids,
        )
        node_ids = [int(item["node_id"]) for item in candidates]
        assert_run_due_guard(
            plan_id=int(plan_id),
            node_ids=node_ids,
            operator=request.operator,
            allow_plan_ids=request.allow_plan_ids,
            allow_node_ids=request.allow_node_ids,
            max_outbound_tasks=request.max_outbound_tasks,
        )
        candidates = candidates[: int(request.max_outbound_tasks)]
        if self._queue_gateway is None:
            from aicrm_next.integration_gateway.wecom_group_adapter import build_group_ops_queue_gateway

            queue_gateway = build_group_ops_queue_gateway()
        else:
            queue_gateway = self._queue_gateway
        job_ids: list[int] = []
        for candidate in candidates:
            job_id = queue_gateway.enqueue_group_message(
                plan_id=int(plan_id),
                source_id=f"{plan_id}:node:{candidate['node_id']}",
                scheduled_at=request.scheduled_at,
                owner_userid=clean_text(plan.get("owner_userid")),
                chat_ids=list(candidate["chat_ids"]),
                content_payload=dict(candidate["content_payload"]),
                content_summary=clean_text(candidate["content_summary"]),
                created_by=clean_text(request.operator),
            )
            job_ids.append(int(job_id))
        return _response(
            {
                "status": "queued",
                "plan_id": int(plan_id),
                "broadcast_job_ids": job_ids,
                "items": candidates,
                "groups": groups,
                "summary": stats,
                "total": len(candidates),
            },
            status_code=202,
            repo=repo,
        )


class GetGroupOpsWebhookConfigQuery:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = _plan_or_404(repo, plan_id)
        if plan.get("plan_type") != "webhook":
            raise ContractError("webhook config is only available for webhook plans")
        webhook_key = clean_text(plan.get("webhook_key"))
        return _response(
            {
                "method": "POST",
                "webhook_url": f"{_public_base_url()}/api/automation/group-ops/webhooks/{webhook_key}",
                "token_status": "generated" if plan.get("webhook_token_hash") else "missing",
            },
            repo=repo,
        )


class RegenerateGroupOpsWebhookCommand:
    def __init__(self, repo: GroupOpsRepository | None = None) -> None:
        self._repo = repo

    def __call__(self, plan_id: int) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = _plan_or_404(repo, plan_id)
        if plan.get("plan_type") != "webhook":
            raise ContractError("webhook config is only available for webhook plans")
        updated = repo.regenerate_webhook(int(plan_id))
        config = GetGroupOpsWebhookConfigQuery(repo)(int(plan_id))
        config["plaintext_token"] = clean_text(updated.get("plaintext_token"))
        config["token_status"] = "generated"
        return config


class ReceiveGroupOpsWebhookCommand:
    def __init__(
        self,
        repo: GroupOpsRepository | None = None,
        queue_gateway: GroupOpsQueueGatewayContract | None = None,
    ) -> None:
        self._repo = repo
        self._queue_gateway = queue_gateway

    def __call__(self, webhook_key: str, request: GroupOpsWebhookReceiveRequest, *, authorization: str | None = None) -> dict[str, Any]:
        repo = _repo_or_block(self._repo)
        if repo is None:
            return _production_unavailable()
        plan = repo.get_plan_by_webhook_key(webhook_key)
        if not plan:
            raise NotFoundError("group ops webhook not found")
        if plan.get("plan_type") != "webhook":
            raise NotFoundError("group ops webhook not found")
        if plan.get("status") != "active":
            raise ConflictError("group ops webhook plan is not active")
        bearer = extract_bearer_token(authorization)
        if not verify_webhook_token(provided_token=bearer, token_hash=clean_text(plan.get("webhook_token_hash"))):
            raise UnauthorizedError("invalid webhook token")
        if clean_text(request.send_mode) not in {"queued"}:
            raise ContractError("send_mode v1 only supports queued")
        if not clean_text(request.idempotency_key):
            raise ContractError("idempotency_key is required")
        duplicate = repo.find_webhook_event(int(plan["id"]), request.idempotency_key)
        if duplicate:
            duplicate = dict(duplicate)
            duplicate["status"] = "duplicate"
            return _response({"status": "duplicate", "event": duplicate, "broadcast_job_ids": duplicate.get("broadcast_job_ids", [])}, repo=repo)
        content = request.content or {}
        attachments = content.get("attachments") if isinstance(content.get("attachments"), list) else []
        normalized_content = normalize_message_content(
            text=content.get("text") or "",
            attachments=attachments,
            sender=clean_text(plan.get("owner_userid")),
        )
        groups = repo.list_bound_groups(int(plan["id"]))
        if not groups:
            raise ConflictError("webhook plan has no bound groups")
        event = repo.create_webhook_event(
            int(plan["id"]),
            {
                "idempotency_key": request.idempotency_key,
                "request_payload": request.model_dump(),
                "normalized_content_payload": normalized_content,
                "scheduled_at": request.scheduled_at or "",
                "status": "accepted",
            },
        )
        chat_ids = [clean_text(item.get("chat_id")) for item in groups if clean_text(item.get("chat_id"))]
        queue_content_payload = dict(normalized_content)
        queue_content_payload["channel"] = "wecom_customer_group"
        queue_content_payload["chat_ids"] = chat_ids
        queue_content_payload["sender"] = clean_text(plan.get("owner_userid"))
        if self._queue_gateway is None:
            from aicrm_next.integration_gateway.wecom_group_adapter import build_group_ops_queue_gateway

            queue_gateway = build_group_ops_queue_gateway()
        else:
            queue_gateway = self._queue_gateway
        try:
            job_id = queue_gateway.enqueue_group_message(
                plan_id=int(plan["id"]),
                source_id=f"{plan['id']}:webhook:{event['id']}",
                scheduled_at=request.scheduled_at,
                owner_userid=clean_text(plan.get("owner_userid")),
                chat_ids=chat_ids,
                content_payload=queue_content_payload,
                content_summary=(normalized_content.get("text") or {}).get("content", "") or f"{len(normalized_content.get('attachments') or [])} attachments",
            )
        except Exception as exc:
            failed = repo.update_webhook_event(
                int(event["id"]),
                {"status": "failed", "error_message": str(exc), "broadcast_job_ids": []},
            )
            return _response({"status": "failed", "event": failed, "broadcast_job_ids": []}, status_code=500, repo=repo)
        queued = repo.update_webhook_event(int(event["id"]), {"status": "queued", "broadcast_job_ids": [int(job_id)]})
        return _response({"status": "queued", "event": queued, "broadcast_job_ids": [int(job_id)]}, status_code=202, repo=repo)
