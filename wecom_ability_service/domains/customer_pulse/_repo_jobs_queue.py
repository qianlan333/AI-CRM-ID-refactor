"""Snapshot / job / queue / recompute data-access for customer_pulse (阶段 5.3).

Extracted from repo.py. Independent leaf module — does not call other repo
groups (cards / actions / feedback / core_other). Cards / actions / feedback /
core_other depend on this module via the main repo facade.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (
    _fetchall_dict,
    _fetchone_dict,
    _json_storage,
    _normalized_text,
    _required_tenant_key,
)


def create_customer_pulse_snapshot(
    *,
    tenant_key: str,
    external_userid: str,
    owner_userid: str,
    snapshot_status: str,
    confidence: float | None,
    priority_score: float,
    summary: str,
    recommended_action_type: str,
    recommended_action_label: str,
    evidence: Any,
    ai_payload: Any,
    signals: Any,
    risk_flags: Any,
    opportunity_flags: Any,
    suggested_action_candidates: Any,
    score_breakdown: Any,
    source_updated_at: str,
    created_by: str,
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    row = db.execute(
        """
        INSERT INTO customer_pulse_snapshots (
            tenant_key,
            external_userid,
            owner_userid,
            snapshot_status,
            confidence,
            priority_score,
            summary,
            recommended_action_type,
            recommended_action_label,
            evidence_json,
            ai_payload_json,
            signals_json,
            risk_flags_json,
            opportunity_flags_json,
            suggested_action_candidates_json,
            score_breakdown_json,
            source_updated_at,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            resolved_tenant_key,
            _normalized_text(external_userid),
            _normalized_text(owner_userid),
            _normalized_text(snapshot_status) or "ready",
            confidence,
            float(priority_score or 0),
            _normalized_text(summary),
            _normalized_text(recommended_action_type),
            _normalized_text(recommended_action_label),
            _json_storage(evidence, default="[]"),
            _json_storage(ai_payload, default="{}"),
            _json_storage(signals, default="[]"),
            _json_storage(risk_flags, default="[]"),
            _json_storage(opportunity_flags, default="[]"),
            _json_storage(suggested_action_candidates, default="[]"),
            _json_storage(score_breakdown, default="[]"),
            _normalized_text(source_updated_at),
            _normalized_text(created_by) or "system",
        ),
    ).fetchone()
    snapshot_id = int((row or {}).get("id") or 0)
    db.commit()
    return get_customer_pulse_snapshot(snapshot_id, tenant_key=resolved_tenant_key) or {}


def get_customer_pulse_snapshot(snapshot_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_snapshots
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(snapshot_id)),
    )


def list_customer_pulse_snapshots_by_ids(
    snapshot_ids: list[int] | tuple[int, ...],
    *,
    tenant_key: str,
) -> dict[int, dict[str, Any]]:
    normalized_ids = sorted({int(item) for item in (snapshot_ids or []) if int(item or 0) > 0})
    if not normalized_ids:
        return {}
    placeholders = ",".join(["?"] * len(normalized_ids))
    clauses = [f"id IN ({placeholders})", "tenant_key = ?"]
    params: list[Any] = [*normalized_ids, _required_tenant_key(tenant_key)]
    rows = _fetchall_dict(
        f"""
        SELECT *
        FROM customer_pulse_snapshots
        WHERE {" AND ".join(clauses)}
        """,
        tuple(params),
    )
    return {
        int(row.get("id") or 0): row
        for row in rows
        if int(row.get("id") or 0) > 0
    }


def get_latest_customer_pulse_snapshot_for_external_userid(external_userid: str, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_snapshots
        WHERE tenant_key = ?
          AND external_userid = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), _normalized_text(external_userid)),
    )


def get_customer_pulse_recompute_job_by_external_userid(
    external_userid: str,
    *,
    job_type: str,
    tenant_key: str,
    statuses: tuple[str, ...] = ("pending", "running"),
) -> dict[str, Any] | None:
    normalized_statuses = tuple(_normalized_text(item) for item in statuses if _normalized_text(item))
    if not normalized_statuses:
        return None
    placeholders = ",".join(["?"] * len(normalized_statuses))
    return _fetchone_dict(
        f"""
        SELECT
            id, job_type, tenant_key, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE job_type = ?
          AND tenant_key = ?
          AND external_userid = ?
          AND status IN ({placeholders})
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalized_text(job_type), _required_tenant_key(tenant_key), _normalized_text(external_userid), *normalized_statuses),
    )


def upsert_customer_pulse_recompute_job(
    *,
    job_type: str,
    tenant_key: str,
    external_userid: str,
    owner_userid: str,
    run_after: str,
    payload: Any,
) -> dict[str, Any]:
    normalized_job_type = _normalized_text(job_type)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_job_type or not normalized_external_userid:
        return {}
    resolved_tenant_key = _required_tenant_key(tenant_key)
    db = get_db()
    existing = get_customer_pulse_recompute_job_by_external_userid(
        normalized_external_userid,
        job_type=normalized_job_type,
        tenant_key=resolved_tenant_key,
        statuses=("pending", "running"),
    )
    if existing and _normalized_text(existing.get("status")) == "pending":
        existing_run_after = _normalized_text(existing.get("run_after"))
        next_run_after = min(existing_run_after, _normalized_text(run_after)) if existing_run_after else _normalized_text(run_after)
        db.execute(
            """
            UPDATE user_ops_deferred_jobs
            SET tenant_key = ?,
                owner_userid = ?,
                run_after = ?,
                payload_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                resolved_tenant_key,
                _normalized_text(owner_userid),
                next_run_after,
                _json_storage(payload, default="{}"),
                int(existing["id"]),
            ),
        )
        db.commit()
        return get_customer_pulse_recompute_job(int(existing["id"]), tenant_key=resolved_tenant_key) or {}
    row = db.execute(
        """
        INSERT INTO user_ops_deferred_jobs (
            job_type,
            tenant_key,
            external_userid,
            owner_userid,
            run_after,
            status,
            attempt_count,
            payload_json,
            result_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            normalized_job_type,
            resolved_tenant_key,
            normalized_external_userid,
            _normalized_text(owner_userid),
            _normalized_text(run_after),
            _json_storage(payload, default="{}"),
        ),
    ).fetchone()
    db.commit()
    return get_customer_pulse_recompute_job(int((row or {}).get("id") or 0), tenant_key=resolved_tenant_key) or {}


def list_due_customer_pulse_recompute_jobs(
    *,
    job_type: str,
    due_at: str,
    tenant_key: str,
    owner_userids: list[str] | tuple[str, ...] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    clauses = ["job_type = ?", "tenant_key = ?", "status = 'pending'", "run_after <= ?"]
    params: list[Any] = [_normalized_text(job_type), _required_tenant_key(tenant_key), _normalized_text(due_at)]
    normalized_owner_userids = [_normalized_text(item) for item in (owner_userids or []) if _normalized_text(item)]
    if normalized_owner_userids:
        placeholders = ",".join(["?"] * len(normalized_owner_userids))
        clauses.append(f"owner_userid IN ({placeholders})")
        params.extend(normalized_owner_userids)
    params.append(max(1, min(int(limit), 200)))
    return _fetchall_dict(
        f"""
        SELECT
            id, job_type, tenant_key, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE {" AND ".join(clauses)}
        ORDER BY run_after ASC, id ASC
        LIMIT ?
        """,
        tuple(params),
    )


def get_customer_pulse_recompute_job(job_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT
            id, job_type, tenant_key, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(job_id)),
    )


def mark_customer_pulse_recompute_job_running(job_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    current = get_customer_pulse_recompute_job(job_id, tenant_key=resolved_tenant_key)
    if not current or _normalized_text(current.get("status")) != "pending":
        return None
    get_db().execute(
        """
        UPDATE user_ops_deferred_jobs
        SET status = 'running',
            attempt_count = COALESCE(attempt_count, 0) + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE tenant_key = ?
          AND id = ?
        """,
        (resolved_tenant_key, int(job_id)),
    )
    get_db().commit()
    return get_customer_pulse_recompute_job(job_id, tenant_key=resolved_tenant_key)


def finish_customer_pulse_recompute_job(job_id: int, *, status: str, result_payload: Any, tenant_key: str) -> dict[str, Any]:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    get_db().execute(
        """
        UPDATE user_ops_deferred_jobs
        SET status = ?,
            result_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE tenant_key = ?
          AND id = ?
        """,
        (
            _normalized_text(status),
            _json_storage(result_payload, default="{}"),
            resolved_tenant_key,
            int(job_id),
        ),
    )
    get_db().commit()
    return get_customer_pulse_recompute_job(job_id, tenant_key=resolved_tenant_key) or {}



__all__ = [
    "create_customer_pulse_snapshot",
    "finish_customer_pulse_recompute_job",
    "get_customer_pulse_recompute_job",
    "get_customer_pulse_recompute_job_by_external_userid",
    "get_customer_pulse_snapshot",
    "get_latest_customer_pulse_snapshot_for_external_userid",
    "list_customer_pulse_snapshots_by_ids",
    "list_due_customer_pulse_recompute_jobs",
    "mark_customer_pulse_recompute_job_running",
    "upsert_customer_pulse_recompute_job",
]
