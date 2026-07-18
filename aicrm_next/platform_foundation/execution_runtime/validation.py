from __future__ import annotations

import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Mapping
from uuid import uuid4

from aicrm_next.platform_foundation.repository import RuntimeReadinessRepository
from aicrm_next.shared.release import current_release_sha
from aicrm_next.shared.runtime_settings import runtime_setting

from ..external_effects.wecom_canary_policy import wecom_canary_job_gate_error
from .repository import normalize_runtime_database_url, open_runtime_connection


CANARY_CONFIG_KEYS = (
    "AICRM_WECOM_PROVIDER_TARGET_POLICY",
    "AICRM_EXTERNAL_EFFECT_ALLOWED_TARGET_EXTERNAL_USERIDS",
    "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS",
    "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS",
    "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_CHAT_IDS",
    "AICRM_WECOM_CANARY_ALLOWED_MEDIA_TARGETS",
    "AICRM_WECOM_DEFAULT_SENDER_USERID",
    "AICRM_WECOM_ENABLED_EFFECT_TYPES",
    "AICRM_WECOM_EXECUTION_MODE",
    "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
    "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY",
    "AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED",
    "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE",
    "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE",
    "AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE",
)
REQUIRED_FAULT_EVIDENCE = frozenset(
    {"listener_reconnect", "worker_restart", "database_reconnect"}
)
REQUIRED_VALIDATION_EVIDENCE = frozenset(
    {
        "test_loopback",
        "wecom_private",
        "wecom_group",
        "wecom_welcome",
        "wecom_tag",
        "wecom_profile",
        "wecom_contact_detail",
        "wecom_media",
        *REQUIRED_FAULT_EVIDENCE,
    }
)
TERMINAL_JOB_STATUSES = frozenset(
    {
        "succeeded",
        "simulated",
        "unknown_after_dispatch",
        "failed_terminal",
        "blocked",
        "cancelled",
        "expired",
    }
)


def canary_configuration_values() -> dict[str, str]:
    return {key: runtime_setting(key, "") for key in CANARY_CONFIG_KEYS}


def configuration_hash(values: Mapping[str, Any] | None = None) -> str:
    source = dict(values or canary_configuration_values())
    canonical = {key: str(source.get(key) or "") for key in CANARY_CONFIG_KEYS}
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evidence_type_for_effect(effect_type: str) -> str:
    return {
        "wecom.message.private.send": "wecom_private",
        "wecom.message.group.send": "wecom_group",
        "wecom.welcome_message.send": "wecom_welcome",
        "wecom.contact.tag.mark": "wecom_tag",
        "wecom.contact.tag.unmark": "wecom_tag",
        "wecom.profile.update": "wecom_profile",
        "wecom.external_contact.detail.fetch": "wecom_contact_detail",
        "wecom.media.upload": "wecom_media",
    }.get(str(effect_type or "").strip(), "")


def resolve_external_effect_job_id(
    database_url: str,
    *,
    execution_id: str,
    requested_job_id: int = 0,
) -> int:
    with open_runtime_connection(normalize_runtime_database_url(database_url)) as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM external_effect_job
            WHERE execution_id = %s
            ORDER BY id
            """,
            (str(execution_id or "").strip(),),
        ).fetchall()
    job_ids = [int(row["id"]) for row in rows]
    if int(requested_job_id or 0):
        if int(requested_job_id) not in job_ids:
            raise RuntimeError("requested job does not belong to the execution")
        return int(requested_job_id)
    if len(job_ids) != 1:
        raise RuntimeError("execution must resolve to exactly one job unless --job-id is supplied")
    return job_ids[0]


def test_loopback_receipt_evidence(repository: Any, job: Any) -> dict[str, Any]:
    receipts, total = repository.list_test_receipts(
        {"job_id": str(job.id)},
        limit=2,
        offset=0,
    )
    receipt = receipts[0] if total == 1 and receipts else None
    expected_hash = str(job.payload_json.get("expected_payload_hash") or "")
    return {
        "test_receipt_count": int(total),
        "test_receipt_signature_valid": bool(receipt and receipt.signature_valid is True),
        "test_receipt_payload_hash_matches": bool(
            receipt and expected_hash and receipt.payload_hash == expected_hash
        ),
        "test_receipt_response_2xx": bool(
            receipt and 200 <= int(receipt.response_status or 0) < 300
        ),
    }


def record_external_effect_evidence(
    database_url: str,
    *,
    job: Any,
    attempts: list[Any],
    release_sha: str,
    generation: int,
    policy_version: str,
    actor: str,
    reason: str,
    evidence_type: str = "",
    extra_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    provider_attempts = [attempt for attempt in attempts if str(attempt.provider_call_started_at or "")]
    normalized_type = str(evidence_type or evidence_type_for_effect(job.effect_type)).strip()
    mapped_type = evidence_type_for_effect(job.effect_type)
    extra = dict(extra_evidence or {})
    is_loopback = normalized_type == "test_loopback"
    evidence_type_matches = bool(
        (is_loopback and str(job.payload_json.get("execution_scope") or "") == "test_loopback")
        or (mapped_type and normalized_type == mapped_type)
    )
    policy_matches = str(job.policy_version or "") == str(policy_version or "")
    policy_proof_valid = policy_matches
    provider_policy_error = "" if is_loopback else wecom_canary_job_gate_error(job)
    receipt_proof_valid = bool(
        not is_loopback
        or (
            int(extra.get("test_receipt_count") or 0) == 1
            and extra.get("test_receipt_signature_valid") is True
            and extra.get("test_receipt_payload_hash_matches") is True
            and extra.get("test_receipt_response_2xx") is True
        )
    )
    passed = bool(
        normalized_type
        and evidence_type_matches
        and policy_proof_valid
        and not provider_policy_error
        and receipt_proof_valid
        and job.status == "succeeded"
        and job.side_effect_executed
        and job.provider_result_received
        and int(job.worker_generation or 0) == int(generation)
        and len(provider_attempts) == 1
        and provider_attempts[0].status == "succeeded"
        and int(provider_attempts[0].worker_generation or 0) == int(generation)
    )
    evidence = {
        "job_status": str(job.status),
        "provider_boundary_started": bool(job.provider_call_started_at),
        "provider_result_received": bool(job.provider_result_received),
        "side_effect_executed": bool(job.side_effect_executed),
        "attempt_count": int(job.attempt_count),
        "provider_attempt_count": len(provider_attempts),
        "duplicate_provider_call_proof": len(provider_attempts) <= 1,
        "worker_generation_matches": int(job.worker_generation or 0) == int(generation),
        "evidence_type_matches": evidence_type_matches,
        "job_policy_version_matches": policy_matches,
        "policy_proof_valid": policy_proof_valid,
        "provider_policy_gate_passed": not provider_policy_error,
        "test_receipt_proof_valid": receipt_proof_valid,
        "execution_scope": str(job.payload_json.get("execution_scope") or ""),
        "target_values_redacted": True,
        **extra,
    }
    with open_runtime_connection(normalize_runtime_database_url(database_url)) as connection:
        connection.execute(
            """
            INSERT INTO queue_runtime_validation_evidence (
                evidence_id, evidence_type, release_sha, active_generation,
                policy_version, execution_id, job_id, status, evidence_json,
                actor, reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                "qrve_" + uuid4().hex,
                normalized_type,
                release_sha,
                int(generation),
                policy_version,
                str(job.execution_id or ""),
                int(job.id),
                "passed" if passed else "failed",
                json.dumps(evidence, sort_keys=True),
                actor,
                reason,
            ),
        )
        connection.commit()
    return {
        "job_id": int(job.id),
        "execution_id": str(job.execution_id or ""),
        "evidence_type": normalized_type,
        "status": "passed" if passed else "failed",
        **evidence,
    }


def record_fault_evidence(
    database_url: str,
    *,
    evidence_type: str,
    release_sha: str,
    generation: int,
    policy_version: str,
    passed: bool,
    evidence: Mapping[str, Any],
    actor: str,
    reason: str,
) -> dict[str, Any]:
    normalized_type = str(evidence_type or "").strip()
    if normalized_type not in REQUIRED_FAULT_EVIDENCE:
        raise ValueError("unsupported queue-runtime fault evidence type")
    public_evidence = {
        **dict(evidence or {}),
        "target_values_redacted": True,
        "secrets_in_evidence": False,
    }
    with open_runtime_connection(normalize_runtime_database_url(database_url)) as connection:
        connection.execute(
            """
            INSERT INTO queue_runtime_validation_evidence (
                evidence_id, evidence_type, release_sha, active_generation,
                policy_version, execution_id, job_id, status, evidence_json,
                actor, reason
            ) VALUES (%s, %s, %s, %s, %s, '', NULL, %s, %s::jsonb, %s, %s)
            """,
            (
                "qrve_" + uuid4().hex,
                normalized_type,
                release_sha,
                int(generation),
                policy_version,
                "passed" if passed else "failed",
                json.dumps(public_evidence, sort_keys=True),
                actor,
                reason,
            ),
        )
        connection.commit()
    return {
        "evidence_type": normalized_type,
        "status": "passed" if passed else "failed",
        **public_evidence,
    }


def _scalar_count(connection: Any, query: str, parameters: tuple[Any, ...]) -> int:
    row = connection.execute(query, parameters).fetchone()
    return int((row or {}).get("count") or 0)


def _lost_lease_count(connection: Any, *, started_at: datetime) -> int:
    """Count every queue row whose lease was lost during this soak window.

    Recovered rows no longer have an expired active lease or a stable error
    marker, so recovery writes an append-only event before mutating queue state.
    Active expirations not yet recovered are added to that durable event count.
    """

    return _scalar_count(
        connection,
        """
        SELECT (
            SELECT COUNT(*)::BIGINT
            FROM queue_runtime_lease_recovery_event
            WHERE detected_at >= %s
        ) + (
            SELECT COUNT(*)::BIGINT
            FROM (
                SELECT id
                FROM external_effect_job
                WHERE status = 'dispatching'
                  AND lease_expires_at >= %s
                  AND lease_expires_at <= CURRENT_TIMESTAMP
                UNION ALL
                SELECT id
                FROM internal_event_consumer_run
                WHERE status = 'running'
                  AND lease_expires_at >= %s
                  AND lease_expires_at <= CURRENT_TIMESTAMP
                UNION ALL
                SELECT id
                FROM internal_event_outbox
                WHERE status = 'running'
                  AND lease_expires_at >= %s
                  AND lease_expires_at <= CURRENT_TIMESTAMP
                UNION ALL
                SELECT id
                FROM webhook_inbox
                WHERE status = 'processing'
                  AND lease_expires_at >= %s
                  AND lease_expires_at <= CURRENT_TIMESTAMP
            ) active_expirations
        ) AS count
        """,
        (started_at,) * 5,
    )


def collect_soak_metrics(
    database_url: str,
    *,
    started_at: datetime,
) -> dict[str, Any]:
    normalized_url = normalize_runtime_database_url(database_url)
    with RuntimeReadinessRepository(normalized_url) as readiness:
        queue_metrics = readiness.queue_metrics()
        migration_revisions = list(readiness.migration_revisions())
    release_sha = current_release_sha()
    with open_runtime_connection(normalized_url) as connection:
        lost_lease_count = _lost_lease_count(connection, started_at=started_at)
        duplicate_provider_call_count = _scalar_count(
            connection,
            """
            SELECT COUNT(*)::BIGINT AS count
            FROM (
                SELECT job_id
                FROM external_effect_attempt
                WHERE provider_call_started_at IS NOT NULL
                  AND provider_call_started_at >= %s
                GROUP BY job_id
                HAVING COUNT(*) > 1
            ) duplicates
            """,
            (started_at,),
        )
        rate_limited_attempt_count = _scalar_count(
            connection,
            """
            SELECT COUNT(*)::BIGINT AS count
            FROM external_effect_attempt
            WHERE provider_call_started_at >= %s
              AND error_code IN ('rate_limited', 'http_429', 'wecom_errcode_45009')
            """,
            (started_at,),
        )
        canary_rows = connection.execute(
            """
            SELECT effect_type, target_id, payload_json, payload_summary_json
            FROM external_effect_job
            WHERE payload_json->>'execution_scope' = 'allowlisted_canary'
              AND side_effect_executed = TRUE
              AND provider_call_started_at >= %s
            """,
            (started_at,),
        ).fetchall()
        unexpected_real_target_count = 0
        for row in canary_rows:
            job = SimpleNamespace(
                effect_type=str(row.get("effect_type") or ""),
                target_id=str(row.get("target_id") or ""),
                payload_json=dict(row.get("payload_json") or {}),
                payload_summary_json=dict(row.get("payload_summary_json") or {}),
            )
            if wecom_canary_job_gate_error(job):
                unexpected_real_target_count += 1
        heartbeat = connection.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE listener_connected = TRUE
                      AND heartbeat_at >= CURRENT_TIMESTAMP - INTERVAL '30 seconds'
                )::BIGINT AS fresh_listener_count,
                COUNT(*) FILTER (
                    WHERE heartbeat_at >= CURRENT_TIMESTAMP - INTERVAL '30 seconds'
                      AND release_sha <> %s
                )::BIGINT AS worker_release_mismatch_count
            FROM queue_worker_heartbeat
            WHERE generation = (
                SELECT active_generation FROM queue_runtime_control WHERE singleton = TRUE
            )
            """,
            (release_sha,),
        ).fetchone()
    return {
        **queue_metrics,
        "migration_revisions": migration_revisions,
        "fresh_listener_count": int((heartbeat or {}).get("fresh_listener_count") or 0),
        "worker_release_mismatch_count": int(
            (heartbeat or {}).get("worker_release_mismatch_count") or 0
        ),
        "lost_lease_count": lost_lease_count,
        "duplicate_provider_call_count": duplicate_provider_call_count,
        "unexpected_real_target_count": unexpected_real_target_count,
        "rate_limited_attempt_count": rate_limited_attempt_count,
    }


def evaluate_soak_snapshot(
    metrics: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    release_matches: bool,
    configuration_matches: bool,
    migration_matches: bool,
) -> list[str]:
    violations: list[str] = []
    if not release_matches:
        violations.append("release_sha_changed")
    if not configuration_matches:
        violations.append("canary_configuration_changed")
    if not migration_matches:
        violations.append("migration_revision_changed")
    for key in (
        "lost_lease_count",
        "duplicate_provider_call_count",
        "unexpected_real_target_count",
        "worker_release_mismatch_count",
    ):
        if int(metrics.get(key) or 0) > 0:
            violations.append(key)
    if int(metrics.get("fresh_listener_count") or 0) < 9:
        violations.append("fresh_listener_count_below_nine")
    if int(metrics.get("queue_unknown_count") or 0) > int(baseline.get("queue_unknown_count") or 0):
        violations.append("unknown_count_increased")
    if int(metrics.get("queue_dlq_count") or 0) > int(baseline.get("queue_dlq_count") or 0):
        violations.append("dlq_count_increased")
    oldest_eligible = max(
        int(metrics.get("external_effect_eligible_oldest_pending_age_seconds") or 0),
        int(metrics.get("internal_event_actionable_oldest_pending_age_seconds") or 0),
        int(metrics.get("webhook_eligible_oldest_pending_age_seconds") or 0),
    )
    if oldest_eligible > 3:
        violations.append("eligible_backlog_exceeded_three_seconds")
    return list(dict.fromkeys(violations))


__all__ = [
    "CANARY_CONFIG_KEYS",
    "REQUIRED_FAULT_EVIDENCE",
    "REQUIRED_VALIDATION_EVIDENCE",
    "TERMINAL_JOB_STATUSES",
    "canary_configuration_values",
    "collect_soak_metrics",
    "configuration_hash",
    "evaluate_soak_snapshot",
    "evidence_type_for_effect",
    "record_external_effect_evidence",
    "record_fault_evidence",
    "resolve_external_effect_job_id",
    "test_loopback_receipt_evidence",
]
