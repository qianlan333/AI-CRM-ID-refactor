from __future__ import annotations

import json
from time import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
from aicrm_next.shared.db_session import get_engine


def _admin_cookies() -> dict[str, str]:
    return {
        SESSION_COOKIE: sign_session(
            {
                "auth_source": "pytest",
                "login_type": "pytest",
                "username": "governance-api-admin",
                "display_name": "Governance API Admin",
                "roles": ["super_admin"],
                "iat": int(time()),
            }
        )
    }


def _draft_payload(*, idempotency_key: str = "governance-draft-create") -> dict:
    return {
        "idempotency_key": idempotency_key,
        "source_plan_id": "plan-safe-governance-1",
        "sanitized_payload": {
            "workspace": "p1_group_ops_workspace",
            "selected_count": 2,
            "preview_only": True,
        },
        "guardrail_summary": {
            "requires_approval": True,
            "requires_allowlist": True,
            "requires_gray_window": True,
            "no_direct_send": True,
            "no_external_call": True,
        },
        "approval_requirements": {
            "approval_required": True,
            "allowlist_required": True,
            "gray_window_required": True,
        },
        "items": [
            {
                "item_type": "plan",
                "item_ref_id": "plan-safe-governance-1",
                "item_order": 0,
                "sanitized_item": {"title": "Governance safe plan", "status": "ready_preview"},
                "guardrail_summary": {"no_direct_send": True},
            }
        ],
    }


def _request_review_payload(*, version: int, snapshot_hash: str, idempotency_key: str = "governance-review-request") -> dict:
    return {
        "version": version,
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": snapshot_hash,
        "review_note": "safe review note",
    }


def _governance_payload(
    *,
    snapshot_hash: str,
    idempotency_key: str = "governance-request-idem",
    allowlist_hash: str = "allowlist-hash-safe-1",
    allowlist_count: int = 2,
    start_at: str = "2026-06-24T10:00:00+00:00",
    end_at: str = "2026-06-24T11:00:00+00:00",
) -> dict:
    return {
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": snapshot_hash,
        "allowlist_summary": {
            "allowlist_hash": allowlist_hash,
            "allowlist_count": allowlist_count,
            "allowlist_summary": {
                "source": "redacted_governance_allowlist",
                "receiver_summary": "count_only",
            },
            "source_reference": {
                "reference_type": "redacted_internal_record",
                "reference_id": "gov-src-safe-1",
            },
        },
        "gray_window": {
            "start_at": start_at,
            "end_at": end_at,
            "timezone": "UTC",
            "metadata": {"window_label": "safe gray window"},
        },
        "request_note": "safe governance request",
    }


def _count(table: str) -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() or 0)


def _ready_draft(next_client: TestClient, *, create_key: str = "ready-draft") -> dict:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key=f"{create_key}-create"),
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    created_payload = created.json()
    reviewed = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created_payload['draft_id']}/request-review",
        json=_request_review_payload(
            version=created_payload["version"],
            snapshot_hash=created_payload["snapshot_hash"],
            idempotency_key=f"{create_key}-request-review",
        ),
        cookies=cookies,
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def _assert_non_execution_response(payload: dict) -> None:
    assert payload["preview_only"] is True
    assert payload["approved"] is False
    assert payload["real_external_call"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["push_center_job_created"] is False
    assert payload["external_effect_job_created"] is False
    assert payload["broadcast_job_created"] is False
    assert payload["internal_event_created"] is False
    assert payload["can_claim_pass_90_plus"] is False
    assert payload["execution_status"] == "not_execution"
    assert payload.get("review_status") not in {"governance_approved", "sent", "completed"}


def test_group_ops_workspace_governance_apis_fail_closed_without_admin_cookie(next_client: TestClient) -> None:
    request = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts/gowd_missing/governance/request",
        json=_governance_payload(snapshot_hash="safe-snapshot"),
    )
    detail = next_client.get("/api/admin/p1/group-ops-workspace/governance/gowg_missing")
    listed = next_client.get("/api/admin/p1/group-ops-workspace/drafts/gowd_missing/governance")

    for response in [request, detail, listed]:
        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "admin_auth_required"
        assert payload["real_external_call_executed"] is False


def test_ready_for_review_draft_can_request_governance_without_execution(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-create")
    before = {
        "reviews": _count("group_ops_workspace_governance_reviews"),
        "steps": _count("group_ops_workspace_governance_review_steps"),
        "allowlist": _count("group_ops_workspace_allowlist_snapshots"),
        "gray_window": _count("group_ops_workspace_gray_window_approvals"),
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
        "outbound_tasks": _count("outbound_tasks"),
    }

    response = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"]),
        cookies=cookies,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["operation"] == "request_governance"
    assert payload["production_write"] is True
    assert payload["production_write_scope"] == "governance_tables_only"
    assert payload["review_status"] == "approval_pending"
    assert {step["step_type"] for step in payload["steps"]} == {
        "operator_approval",
        "receiver_allowlist",
        "gray_window",
    }
    assert {step["step_status"] for step in payload["steps"]} == {"pending"}
    assert payload["allowlist_summary"]["hash"] == "allowlist-hash-safe-1"
    assert payload["allowlist_summary"]["count"] == 2
    assert payload["gray_window"]["window_status"] == "pending"
    _assert_non_execution_response(payload)

    assert _count("group_ops_workspace_governance_reviews") == before["reviews"] + 1
    assert _count("group_ops_workspace_governance_review_steps") == before["steps"] + 3
    assert _count("group_ops_workspace_allowlist_snapshots") == before["allowlist"] + 1
    assert _count("group_ops_workspace_gray_window_approvals") == before["gray_window"] + 1
    assert _count("external_effect_job") == before["external_effect_job"]
    assert _count("broadcast_jobs") == before["broadcast_jobs"]
    assert _count("internal_event") == before["internal_event"]
    assert _count("outbound_tasks") == before["outbound_tasks"]


def test_governance_request_preconditions_reject_non_ready_archived_snapshot_and_invalid_window(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    draft = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key="governance-not-ready"),
        cookies=cookies,
    ).json()
    not_ready = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{draft['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=draft["snapshot_hash"], idempotency_key="not-ready-governance"),
        cookies=cookies,
    )

    archived_draft = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key="governance-archived"),
        cookies=cookies,
    ).json()
    next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{archived_draft['draft_id']}/archive",
        json={"version": archived_draft["version"], "archive_reason": "safe archive"},
        cookies=cookies,
    )
    archived = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{archived_draft['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=archived_draft["snapshot_hash"], idempotency_key="archived-governance"),
        cookies=cookies,
    )

    ready = _ready_draft(next_client, create_key="governance-invalid")
    snapshot_conflict = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash="different-safe-snapshot", idempotency_key="snapshot-conflict"),
        cookies=cookies,
    )
    invalid_window = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(
            snapshot_hash=ready["snapshot_hash"],
            idempotency_key="invalid-window",
            start_at="2026-06-24T11:00:00+00:00",
            end_at="2026-06-24T10:00:00+00:00",
        ),
        cookies=cookies,
    )
    missing_allowlist_hash = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="missing-allowlist", allowlist_hash=""),
        cookies=cookies,
    )

    assert not_ready.status_code == 400, not_ready.text
    assert archived.status_code in {400, 409}, archived.text
    assert snapshot_conflict.status_code == 400, snapshot_conflict.text
    assert invalid_window.status_code == 400, invalid_window.text
    assert missing_allowlist_hash.status_code == 400, missing_allowlist_hash.text
    assert _count("group_ops_workspace_governance_reviews") == 0
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_governance_request_idempotency_and_active_review_conflicts(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-idempotency")
    payload = _governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="same-governance-key")

    first = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=payload,
        cookies=cookies,
    )
    replay = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=payload,
        cookies=cookies,
    )
    changed_same_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={**payload, "request_note": "changed safe governance note"},
        cookies=cookies,
    )
    different_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="different-governance-key"),
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert changed_same_key.status_code == 409, changed_same_key.text
    assert different_key.status_code == 409, different_key.text
    assert first.json()["review_id"] == replay.json()["review_id"]
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["production_write"] is False
    assert _count("group_ops_workspace_governance_reviews") == 1
    assert _count("group_ops_workspace_governance_review_steps") == 3
    assert _count("group_ops_workspace_allowlist_snapshots") == 1
    assert _count("group_ops_workspace_gray_window_approvals") == 1


def test_governance_request_rejects_sensitive_fields_and_values(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-sensitive")
    sensitive_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={**_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="sensitive-key"), "raw_external_userid": "wm_unsafe"},
        cookies=cookies,
    )
    sensitive_value = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={
            **_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="sensitive-value"),
            "allowlist_summary": {
                "allowlist_hash": "allowlist-hash-safe-sensitive",
                "allowlist_count": 1,
                "allowlist_summary": {"summary": "call 13800138000"},
                "source_reference": {"reference_id": "gov-src-safe"},
            },
        },
        cookies=cookies,
    )
    sensitive_note = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={
            **_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="sensitive-note"),
            "request_note": "contains Authorization: Bearer abc",
        },
        cookies=cookies,
    )

    assert sensitive_key.status_code == 400, sensitive_key.text
    assert sensitive_value.status_code == 400, sensitive_value.text
    assert sensitive_note.status_code == 400, sensitive_note.text
    assert "sensitive" in sensitive_key.json()["detail"]
    assert "sensitive" in sensitive_value.json()["detail"]
    assert "sensitive" in sensitive_note.json()["detail"]
    assert _count("group_ops_workspace_governance_reviews") == 0


def test_get_governance_returns_sanitized_summary_only(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-read")
    created = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="read-governance-key"),
        cookies=cookies,
    ).json()

    detail = next_client.get(
        f"/api/admin/p1/group-ops-workspace/governance/{created['review_id']}",
        cookies=cookies,
    )
    listed = next_client.get(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance",
        cookies=cookies,
    )

    assert detail.status_code == 200, detail.text
    assert listed.status_code == 200, listed.text
    detail_payload = detail.json()
    listed_payload = listed.json()
    assert detail_payload["operation"] == "get_governance"
    assert listed_payload["total"] == 1
    assert listed_payload["items"][0]["review_id"] == created["review_id"]
    _assert_non_execution_response(detail_payload)
    _assert_non_execution_response(listed_payload["items"][0])

    rendered = json.dumps({"detail": detail_payload, "listed": listed_payload}, ensure_ascii=False).lower()
    for forbidden in [
        "raw_external_userid",
        "13800138000",
        "authorization",
        "bearer",
        "secret",
        "openid",
        "unionid",
        "raw message",
        "raw callback",
    ]:
        assert forbidden not in rendered


def test_governance_api_does_not_break_legacy_group_ops_read_routes(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    response = next_client.get("/api/admin/automation-conversion/group-ops/plans?limit=1")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
