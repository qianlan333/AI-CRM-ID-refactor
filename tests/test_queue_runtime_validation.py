from __future__ import annotations

import json
from pathlib import Path

from aicrm_next.platform_foundation.execution_runtime.validation import (
    CANARY_CONFIG_KEYS,
    REQUIRED_VALIDATION_EVIDENCE,
    configuration_hash,
    evaluate_soak_snapshot,
    evidence_type_for_effect,
    record_external_effect_evidence,
)
from aicrm_next.platform_foundation.external_effects.models import (
    ExternalEffectAttempt,
    ExternalEffectJob,
)
from scripts.ops import manage_queue_runtime_soak


ROOT = Path(__file__).resolve().parents[1]


class _EvidenceConnection:
    def __init__(self) -> None:
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, _query, parameters):
        self.parameters = parameters
        return self

    def commit(self) -> None:
        return None


def _healthy_metrics() -> dict:
    return {
        "fresh_listener_count": 9,
        "lost_lease_count": 0,
        "duplicate_provider_call_count": 0,
        "unexpected_real_target_count": 0,
        "worker_release_mismatch_count": 0,
        "queue_unknown_count": 3,
        "queue_dlq_count": 5,
        "external_effect_eligible_oldest_pending_age_seconds": 0,
        "internal_event_actionable_oldest_pending_age_seconds": 0,
        "webhook_eligible_oldest_pending_age_seconds": 0,
    }


def test_configuration_hash_is_stable_and_sensitive_to_every_tracked_value() -> None:
    first = {key: "value" for key in CANARY_CONFIG_KEYS}
    second = dict(first)
    second[CANARY_CONFIG_KEYS[-1]] = "changed"

    assert len(configuration_hash(first)) == 64
    assert configuration_hash(first) == configuration_hash(dict(reversed(list(first.items()))))
    assert configuration_hash(first) != configuration_hash(second)
    assert "AICRM_WECOM_PRIVATE_ADAPTER_MODE" in CANARY_CONFIG_KEYS
    assert "AICRM_WECOM_GROUP_ADAPTER_MODE" in CANARY_CONFIG_KEYS


def test_soak_snapshot_requires_exact_context_and_zero_correctness_regressions() -> None:
    baseline = _healthy_metrics()
    assert (
        evaluate_soak_snapshot(
            _healthy_metrics(),
            baseline,
            release_matches=True,
            configuration_matches=True,
            migration_matches=True,
        )
        == []
    )

    failed = _healthy_metrics()
    failed.update(
        {
            "fresh_listener_count": 8,
            "duplicate_provider_call_count": 1,
            "queue_unknown_count": 4,
            "external_effect_eligible_oldest_pending_age_seconds": 4,
        }
    )
    violations = evaluate_soak_snapshot(
        failed,
        baseline,
        release_matches=False,
        configuration_matches=False,
        migration_matches=False,
    )

    assert set(violations) == {
        "release_sha_changed",
        "canary_configuration_changed",
        "migration_revision_changed",
        "duplicate_provider_call_count",
        "fresh_listener_count_below_nine",
        "unknown_count_increased",
        "eligible_backlog_exceeded_three_seconds",
    }


def test_72_hour_soak_snapshot_coverage_rounds_up_to_at_least_ninety_five_percent() -> None:
    assert manage_queue_runtime_soak._required_snapshot_count(72 * 60 * 60) == 274
    assert manage_queue_runtime_soak._required_snapshot_count(1) == 1


def test_validation_evidence_covers_each_real_canary_and_fault_drill() -> None:
    mapped = {
        evidence_type_for_effect("wecom.message.private.send"),
        evidence_type_for_effect("wecom.message.group.send"),
        evidence_type_for_effect("wecom.welcome_message.send"),
        evidence_type_for_effect("wecom.contact.tag.mark"),
        evidence_type_for_effect("wecom.profile.update"),
        evidence_type_for_effect("wecom.external_contact.detail.fetch"),
        evidence_type_for_effect("wecom.media.upload"),
    }

    assert mapped.issubset(REQUIRED_VALIDATION_EVIDENCE)
    assert {
        "test_loopback",
        "listener_reconnect",
        "worker_restart",
        "database_reconnect",
    }.issubset(REQUIRED_VALIDATION_EVIDENCE)


def test_external_effect_evidence_requires_exact_policy_generation_and_provider_attempt(
    monkeypatch,
) -> None:
    connection = _EvidenceConnection()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.normalize_runtime_database_url",
        lambda value: value,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.open_runtime_connection",
        lambda _value: connection,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.wecom_canary_job_gate_error",
        lambda _job: "",
    )
    job = ExternalEffectJob(
        id=91,
        effect_type="wecom.message.private.send",
        execution_id="exe_canary",
        payload_json={"execution_scope": "allowlisted_canary"},
        status="succeeded",
        policy_version="queue-v2-allowlisted",
        worker_generation=17,
        provider_call_started_at="2026-07-17T00:00:00Z",
        side_effect_executed=True,
        provider_result_received=True,
        attempt_count=1,
    )
    attempts = [
        ExternalEffectAttempt(
            job_id=91,
            provider_call_started_at="2026-07-17T00:00:00Z",
            worker_generation=17,
            status="succeeded",
        )
    ]

    passed = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
        actor="pytest",
        reason="provider proof",
    )
    wrong_policy = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-other",
        actor="pytest",
        reason="provider proof",
    )

    assert passed["status"] == "passed"
    assert passed["provider_attempt_count"] == 1
    assert passed["provider_policy_gate_passed"] is True
    assert wrong_policy["status"] == "failed"
    assert wrong_policy["policy_proof_valid"] is False


def test_external_effect_evidence_exposes_only_stable_redacted_failure_diagnostics(
    monkeypatch,
) -> None:
    connection = _EvidenceConnection()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.normalize_runtime_database_url",
        lambda value: value,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.open_runtime_connection",
        lambda _value: connection,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.wecom_canary_job_gate_error",
        lambda _job: "",
    )
    job = ExternalEffectJob(
        id=93,
        effect_type="wecom.media.upload",
        execution_id="exe_failed_canary",
        payload_json={"execution_scope": "allowlisted_canary"},
        status="failed_terminal",
        policy_version="queue-v2-allowlisted",
        worker_generation=17,
        provider_call_started_at="2026-07-17T00:00:00Z",
        side_effect_executed=False,
        provider_result_received=False,
        attempt_count=1,
        last_error_code="material_not_found",
        last_error_message="secret-bearing provider text must never be exposed",
    )
    attempts = [
        ExternalEffectAttempt(
            job_id=93,
            adapter_mode="execute",
            provider_call_started_at="2026-07-17T00:00:00Z",
            worker_generation=17,
            status="failed_terminal",
            error_code="material_not_found",
            error_message="secret-bearing attempt text must never be exposed",
            response_summary_json={
                "adapter_mode": "production",
                "provider_error_classification": "blocked",
                "errcode": 40096,
                "http_status": 400,
                "execution_gate": "",
                "blocked": True,
                "provider_payload": "must-not-appear",
            },
        )
    ]

    result = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
        actor="pytest",
        reason="safe failure diagnostics",
        extra_evidence={
            "target_values_redacted": False,
            "error_messages_redacted": False,
            "provider_adapter_mode": "fake",
        },
    )

    assert result["status"] == "failed"
    assert result["job_error_code"] == "material_not_found"
    assert result["provider_adapter_mode"] == "production"
    assert result["provider_attempt_status"] == "failed_terminal"
    assert result["provider_attempt_error_code"] == "material_not_found"
    assert result["provider_error_classification"] == "blocked"
    assert result["provider_errcode"] == 40096
    assert result["provider_http_status"] == 400
    assert result["provider_blocked"] is True
    assert result["target_values_redacted"] is True
    assert result["error_messages_redacted"] is True
    serialized = json.dumps(result, sort_keys=True)
    assert "secret-bearing" not in serialized
    assert "must-not-appear" not in serialized


def test_mirrored_welcome_41050_requires_exact_operator_delivery_attestation(
    monkeypatch,
) -> None:
    connection = _EvidenceConnection()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.normalize_runtime_database_url",
        lambda value: value,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.open_runtime_connection",
        lambda _value: connection,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.wecom_canary_job_gate_error",
        lambda _job: "",
    )
    job = ExternalEffectJob(
        id=94,
        effect_type="wecom.welcome_message.send",
        execution_id="exe_mirrored_welcome",
        payload_json={"execution_scope": "allowlisted_canary"},
        status="failed_terminal",
        policy_version="queue-v2-allowlisted",
        worker_generation=17,
        provider_call_started_at="2026-07-19T15:10:27Z",
        side_effect_executed=True,
        provider_result_received=True,
        attempt_count=1,
        last_error_code="wecom_error_41050",
    )
    attempts = [
        ExternalEffectAttempt(
            job_id=94,
            adapter_mode="execute",
            provider_call_started_at="2026-07-19T15:10:27Z",
            worker_generation=17,
            status="failed_terminal",
            error_code="wecom_error_41050",
            response_summary_json={
                "adapter_mode": "execute",
                "provider_error_classification": "terminal",
                "errcode": 41050,
                "blocked": False,
            },
        )
    ]
    callback_proof = {
        "source_webhook_inbox_id": 3810,
        "callback_duplicate_count": 0,
        "callback_to_provider_boundary_ms": 1948,
    }

    pending = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
        actor="pytest",
        reason="mirrored welcome provider result",
        extra_evidence=callback_proof,
    )
    attested = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
        actor="pytest",
        reason="operator observed production welcome delivery",
        extra_evidence={
            **callback_proof,
            "upstream_welcome_delivery_attested": True,
        },
    )

    assert pending["status"] == "failed"
    assert pending["upstream_welcome_attestation_eligible"] is True
    assert pending["upstream_welcome_delivery_attested"] is False
    assert attested["status"] == "passed"
    assert attested["delivery_proof_mode"] == "upstream_operator_attested"


def test_mirrored_welcome_attestation_stays_failed_outside_exact_safety_window(
    monkeypatch,
) -> None:
    connection = _EvidenceConnection()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.normalize_runtime_database_url",
        lambda value: value,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.open_runtime_connection",
        lambda _value: connection,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.wecom_canary_job_gate_error",
        lambda _job: "",
    )
    job = ExternalEffectJob(
        id=95,
        effect_type="wecom.welcome_message.send",
        execution_id="exe_late_welcome",
        payload_json={"execution_scope": "allowlisted_canary"},
        status="failed_terminal",
        policy_version="queue-v2-allowlisted",
        worker_generation=17,
        provider_call_started_at="2026-07-19T15:10:27Z",
        side_effect_executed=True,
        provider_result_received=True,
        attempt_count=1,
        last_error_code="wecom_error_41050",
    )
    attempts = [
        ExternalEffectAttempt(
            job_id=95,
            adapter_mode="execute",
            provider_call_started_at="2026-07-19T15:10:27Z",
            worker_generation=17,
            status="failed_terminal",
            error_code="wecom_error_41050",
            response_summary_json={
                "adapter_mode": "execute",
                "provider_error_classification": "terminal",
                "errcode": 41050,
                "blocked": False,
            },
        )
    ]

    result = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
        actor="pytest",
        reason="late welcome must fail closed",
        extra_evidence={
            "source_webhook_inbox_id": 3811,
            "callback_duplicate_count": 0,
            "callback_to_provider_boundary_ms": 20_000,
            "upstream_welcome_delivery_attested": True,
        },
    )

    assert result["status"] == "failed"
    assert result["upstream_welcome_attestation_eligible"] is False


def test_loopback_evidence_requires_exact_signed_receipt_and_policy(
    monkeypatch,
) -> None:
    connection = _EvidenceConnection()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.normalize_runtime_database_url",
        lambda value: value,
    )
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.execution_runtime.validation.open_runtime_connection",
        lambda _value: connection,
    )
    job = ExternalEffectJob(
        id=92,
        effect_type="questionnaire.submission.webhook.push",
        execution_id="exe_loopback",
        payload_json={"execution_scope": "test_loopback"},
        status="succeeded",
        policy_version="queue-v2-test-loopback",
        worker_generation=17,
        provider_call_started_at="2026-07-17T00:00:00Z",
        side_effect_executed=True,
        provider_result_received=True,
        attempt_count=1,
    )
    attempts = [
        ExternalEffectAttempt(
            job_id=92,
            provider_call_started_at="2026-07-17T00:00:00Z",
            worker_generation=17,
            status="succeeded",
        )
    ]
    receipt_proof = {
        "test_receipt_count": 1,
        "test_receipt_signature_valid": True,
        "test_receipt_payload_hash_matches": True,
        "test_receipt_response_2xx": True,
    }

    missing_receipt = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-test-loopback",
        actor="pytest",
        reason="loopback proof",
        evidence_type="test_loopback",
    )
    exact_policy = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-test-loopback",
        actor="pytest",
        reason="exact loopback proof",
        evidence_type="test_loopback",
        extra_evidence=receipt_proof,
    )
    wrong_policy = record_external_effect_evidence(
        "postgresql://runtime",
        job=job,
        attempts=attempts,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
        actor="pytest",
        reason="wrong policy loopback proof",
        evidence_type="test_loopback",
        extra_evidence=receipt_proof,
    )

    assert missing_receipt["status"] == "failed"
    assert missing_receipt["test_receipt_proof_valid"] is False
    assert exact_policy["status"] == "passed"
    assert exact_policy["policy_proof_valid"] is True
    assert wrong_policy["status"] == "failed"
    assert wrong_policy["policy_proof_valid"] is False


def test_soak_snapshot_timer_is_a_non_executor_fifteen_minute_evidence_writer() -> None:
    manifest = json.loads((ROOT / "deploy" / "production_runtime_units.json").read_text())
    active = {item["timer"]: item["service"] for item in manifest["active_autostart"]}
    timer = (ROOT / "deploy" / "aicrm-queue-soak-snapshot.timer").read_text()
    service = (ROOT / "deploy" / "aicrm-queue-soak-snapshot.service").read_text()

    assert active["aicrm-queue-soak-snapshot.timer"] == "aicrm-queue-soak-snapshot.service"
    assert "OnCalendar=*:0/15" in timer
    assert "Persistent=true" in timer
    assert "manage_queue_runtime_soak.py --action snapshot" in service
    for forbidden in ("run_execution_runtime.py", "dispatch_one", "run_due", "--execute"):
        assert forbidden not in service
