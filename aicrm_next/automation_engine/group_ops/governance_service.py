from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import uuid4

from aicrm_next.shared.errors import ContractError, NotFoundError

from .draft_service import _actor_id, _actor_label, _actor_metadata, _raise_if_sensitive, _text
from .governance_repository import (
    GroupOpsWorkspaceGovernanceRepository,
    build_group_ops_workspace_governance_repository,
)


REQUIRED_STEP_TYPES = ("operator_approval", "receiver_allowlist", "gray_window")


def _json_clone(value: Any, default: Any) -> Any:
    if value is None:
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    return deepcopy(default)


def _canonical_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_datetime(value: Any, *, field: str) -> datetime:
    raw = _text(value)
    if not raw:
        raise ContractError(f"{field} is required")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO datetime") from exc


def _normalize_allowlist_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("allowlist_summary is required")
    _raise_if_sensitive(value)
    allowlist_hash = _text(value.get("allowlist_hash"))
    if not allowlist_hash:
        raise ContractError("allowlist_hash is required")
    try:
        allowlist_count = int(value.get("allowlist_count"))
    except (TypeError, ValueError) as exc:
        raise ContractError("allowlist_count is required") from exc
    if allowlist_count < 0:
        raise ContractError("allowlist_count must be non-negative")
    allowlist_summary = _json_clone(value.get("allowlist_summary"), {})
    source_reference = _json_clone(value.get("source_reference"), {})
    normalized = {
        "allowlist_hash": allowlist_hash,
        "allowlist_count": allowlist_count,
        "allowlist_summary": allowlist_summary,
        "source_reference": source_reference,
        "expires_at": _text(value.get("expires_at")) or None,
    }
    _raise_if_sensitive(normalized)
    return normalized


def _normalize_gray_window(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("gray_window is required")
    _raise_if_sensitive(value)
    start_at = _parse_datetime(value.get("start_at"), field="gray_window.start_at")
    end_at = _parse_datetime(value.get("end_at"), field="gray_window.end_at")
    if end_at <= start_at:
        raise ContractError("gray_window end_at must be after start_at")
    timezone = _text(value.get("timezone")) or "UTC"
    metadata = _json_clone(value.get("metadata"), {})
    normalized = {
        "start_at": start_at,
        "end_at": end_at,
        "timezone": timezone,
        "metadata": metadata,
    }
    _raise_if_sensitive(normalized)
    return normalized


def _normalize_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    _raise_if_sensitive(payload)
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise ContractError("idempotency_key is required")
    client_snapshot_hash = _text(payload.get("client_snapshot_hash"))
    if not client_snapshot_hash:
        raise ContractError("client_snapshot_hash is required")
    request_note = _text(payload.get("request_note"))
    allowlist = _normalize_allowlist_summary(payload.get("allowlist_summary"))
    gray_window = _normalize_gray_window(payload.get("gray_window"))
    normalized = {
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": client_snapshot_hash,
        "allowlist_summary": allowlist,
        "gray_window": {
            **gray_window,
            "start_at": gray_window["start_at"].isoformat(),
            "end_at": gray_window["end_at"].isoformat(),
        },
        "request_note_present": bool(request_note),
        "request_note_hash": _hash({"request_note": request_note}) if request_note else "",
    }
    return {
        **normalized,
        "request_payload_hash": _hash(normalized),
        "gray_window_parsed": gray_window,
    }


def _review_envelope(
    review: dict[str, Any],
    *,
    operation: str,
    production_write: bool,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "review_id": review.get("review_id"),
        "draft_id": review.get("draft_id"),
        "review_status": review.get("review_status"),
        "steps": [
            {
                "step_type": step.get("step_type"),
                "step_status": step.get("step_status"),
                "actor_metadata": {
                    "actor_label_present": bool(step.get("actor_label")),
                    "actor_id_present": bool(step.get("actor_id")),
                },
                "created_at": step.get("created_at"),
                "updated_at": step.get("updated_at"),
            }
            for step in review.get("steps") or []
        ],
        "allowlist_summary": {
            "hash": (review.get("allowlist_summary") or {}).get("allowlist_hash", ""),
            "count": (review.get("allowlist_summary") or {}).get("allowlist_count", 0),
            "source_reference_summary": (review.get("allowlist_summary") or {}).get("source_reference", {}),
            "expires_at": (review.get("allowlist_summary") or {}).get("expires_at", ""),
        },
        "gray_window": {
            "start_at": (review.get("gray_window") or {}).get("start_at", ""),
            "end_at": (review.get("gray_window") or {}).get("end_at", ""),
            "timezone": (review.get("gray_window") or {}).get("timezone", ""),
            "window_status": (review.get("gray_window") or {}).get("window_status", ""),
        },
        "created_at": review.get("created_at"),
        "updated_at": review.get("updated_at"),
        "expires_at": review.get("expires_at"),
        "preview_only": True,
        "production_write": production_write,
        "production_write_scope": "governance_tables_only" if production_write else "none",
        "approved": False,
        "ready_for_review": True,
        "push_center_job_created": False,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
        "real_external_call": False,
        "real_external_call_executed": False,
        "can_claim_pass_90_plus": False,
        "execution_status": "not_execution",
        "idempotent_replay": idempotent_replay,
        "route_owner": "ai_crm_next",
        "capability_owner": "automation_engine",
    }


class GroupOpsWorkspaceGovernanceService:
    def __init__(self, repo: GroupOpsWorkspaceGovernanceRepository | None = None) -> None:
        self.repo = repo or build_group_ops_workspace_governance_repository()

    def request_governance(self, draft_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_request_payload(payload)
        current = self.repo.get_draft(_text(draft_id))
        if not current:
            raise NotFoundError("draft not found")
        if current.get("draft_status") == "archived":
            raise ContractError("archived draft cannot request governance")
        if current.get("draft_status") == "rejected":
            raise ContractError("rejected draft cannot request governance")
        if current.get("draft_status") != "ready_for_review":
            raise ContractError("draft must be ready_for_review before governance request")
        if not _text(current.get("snapshot_hash")):
            raise ContractError("draft snapshot_hash is required")
        if not isinstance(current.get("sanitized_payload"), dict):
            raise ContractError("draft sanitized payload is required")
        if normalized["client_snapshot_hash"] != _text(current.get("snapshot_hash")):
            raise ContractError("draft snapshot conflict")

        existing = self.repo.find_by_idempotency_key(
            draft_id=_text(draft_id),
            idempotency_key=normalized["idempotency_key"],
        )
        if existing:
            metadata = existing.get("audit_metadata") or {}
            if metadata.get("request_payload_hash") != normalized["request_payload_hash"]:
                raise ContractError("governance request idempotency key conflict")
            return _review_envelope(existing, operation="request_governance", production_write=False, idempotent_replay=True)

        active_review = self.repo.find_active_review_for_draft(_text(draft_id))
        if active_review:
            raise ContractError("active governance review exists")

        review_id = f"gowg_{uuid4().hex}"
        actor_id = _actor_id(actor)
        actor_label = _actor_label(actor)
        audit_metadata = {
            "actor": {
                "actor_id": actor_id,
                "actor_label": actor_label,
                "actor_metadata": _actor_metadata(actor),
            },
            "action": "governance_request",
            "draft_id": _text(draft_id),
            "review_id": review_id,
            "snapshot_hash": current["snapshot_hash"],
            "sanitized_payload_hash": _hash(current.get("sanitized_payload") or {}),
            "allowlist_hash": normalized["allowlist_summary"]["allowlist_hash"],
            "allowlist_count": normalized["allowlist_summary"]["allowlist_count"],
            "gray_window": {
                "start_at": normalized["gray_window"]["start_at"],
                "end_at": normalized["gray_window"]["end_at"],
                "timezone": normalized["gray_window"]["timezone"],
            },
            "request_payload_hash": normalized["request_payload_hash"],
            "approved": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
        }
        created = self.repo.create_governance_review(
            {
                "review_id": review_id,
                "draft_id": _text(draft_id),
                "requested_by": actor_id,
                "actor_label": actor_label,
                "idempotency_key": normalized["idempotency_key"],
                "snapshot_hash": current["snapshot_hash"],
                "sanitized_payload_hash": _hash(current.get("sanitized_payload") or {}),
                "audit_metadata": audit_metadata,
                "expires_at": normalized["allowlist_summary"].get("expires_at"),
                "steps": [
                    {
                        "step_id": f"gowgs_{uuid4().hex}",
                        "step_type": step_type,
                        "metadata": {
                            "action": "governance_request",
                            "draft_id": _text(draft_id),
                            "review_id": review_id,
                            "step_type": step_type,
                        },
                    }
                    for step_type in REQUIRED_STEP_TYPES
                ],
                "allowlist_snapshot": {
                    "snapshot_id": f"gowas_{uuid4().hex}",
                    **normalized["allowlist_summary"],
                },
                "gray_window": {
                    "approval_id": f"gowgw_{uuid4().hex}",
                    **normalized["gray_window_parsed"],
                    "metadata": {
                        "action": "governance_request",
                        "draft_id": _text(draft_id),
                        "review_id": review_id,
                        "window_status": "pending",
                    },
                },
            }
        )
        return _review_envelope(created, operation="request_governance", production_write=True)

    def get_review(self, review_id: str) -> dict[str, Any]:
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        return _review_envelope(review, operation="get_governance", production_write=False)

    def list_reviews_for_draft(self, draft_id: str) -> dict[str, Any]:
        reviews = self.repo.list_reviews_for_draft(_text(draft_id))
        return {
            "ok": True,
            "items": [_review_envelope(review, operation="list_item", production_write=False) for review in reviews],
            "total": len(reviews),
            "preview_only": True,
            "production_write": False,
            "real_external_call": False,
            "real_external_call_executed": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
            "can_claim_pass_90_plus": False,
            "execution_status": "not_execution",
            "route_owner": "ai_crm_next",
            "capability_owner": "automation_engine",
        }
