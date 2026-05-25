from __future__ import annotations

import os
from typing import Any

from aicrm_next.integration_gateway.wecom_group_contract import GroupOpsQueueGatewayContract
from aicrm_next.shared.errors import ApplicationError, ContractError, NotFoundError
from aicrm_next.shared.repository_provider import blocked_production_payload

from . import CAPABILITY_OWNER
from .domain import (
    assert_group_owned_by_plan,
    binding_stats,
    clean_text,
    clamp_limit,
    extract_bearer_token,
    normalize_message_content,
    normalize_node_payload,
    verify_webhook_token,
)
from .dto import (
    GroupOpsBindGroupRequest,
    GroupOpsGroupsRequest,
    GroupOpsNodeRequest,
    GroupOpsPlanCreateRequest,
    GroupOpsPlanListRequest,
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
        return _response({"items": items, "total": total}, repo=repo)


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
        repo.regenerate_webhook(int(plan_id))
        return GetGroupOpsWebhookConfigQuery(repo)(int(plan_id))


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
                content_payload=normalized_content,
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
