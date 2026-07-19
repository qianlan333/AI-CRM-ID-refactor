from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from aicrm_next.platform_foundation.execution_runtime import validation
from scripts.ops import attest_queue_runtime_validation


class _Rows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Connection:
    def __init__(self, rows) -> None:
        self._rows = rows

    def execute(self, _query, _parameters):
        return _Rows(self._rows)


def test_attestation_plan_is_redacted_and_does_not_open_the_database(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        attest_queue_runtime_validation,
        "RuntimeGenerationRepository",
        lambda *_args, **_kwargs: pytest.fail("plan-only mode must not open the database"),
    )

    assert (
        attest_queue_runtime_validation.main(
            [
                "--execution-id",
                "exe_canary_001",
                "--expected-release-sha",
                "a" * 40,
                "--generation",
                "17",
                "--expected-policy-version",
                "queue-v2-allowlisted",
                "--actor",
                "pytest",
                "--reason",
                "plan only",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"applied": false' in output
    assert '"target_values_redacted": true' in output
    assert '"real_external_call_executed": false' in output


def test_job_selection_requires_exact_execution_or_explicit_member(monkeypatch) -> None:
    monkeypatch.setattr(
        validation,
        "open_runtime_connection",
        lambda _url: nullcontext(_Connection([{"id": 11}, {"id": 12}])),
    )
    monkeypatch.setattr(validation, "normalize_runtime_database_url", lambda value: value)

    with pytest.raises(RuntimeError, match="exactly one job"):
        validation.resolve_external_effect_job_id(
            "postgresql://runtime",
            execution_id="exe_multi",
            requested_job_id=0,
        )
    assert (
        validation.resolve_external_effect_job_id(
            "postgresql://runtime",
            execution_id="exe_multi",
            requested_job_id=12,
        )
        == 12
    )
    with pytest.raises(RuntimeError, match="does not belong"):
        validation.resolve_external_effect_job_id(
            "postgresql://runtime",
            execution_id="exe_multi",
            requested_job_id=13,
        )


def test_mirrored_welcome_attestation_context_requires_latest_exact_failed_evidence(
    monkeypatch,
) -> None:
    row = {
        "evidence_id": "qrve_source",
        "status": "failed",
        "evidence_json": {
            "upstream_welcome_attestation_eligible": True,
            "source_webhook_inbox_id": 3810,
            "callback_duplicate_count": 0,
            "callback_to_provider_boundary_ms": 1948,
        },
    }
    monkeypatch.setattr(
        validation,
        "open_runtime_connection",
        lambda _url: nullcontext(_Connection([row])),
    )
    monkeypatch.setattr(validation, "normalize_runtime_database_url", lambda value: value)

    result = validation.mirrored_welcome_attestation_context(
        "postgresql://runtime",
        job_id=94,
        release_sha="a" * 40,
        generation=17,
        policy_version="queue-v2-allowlisted",
    )

    assert result == {
        "source_webhook_inbox_id": 3810,
        "callback_duplicate_count": 0,
        "callback_to_provider_boundary_ms": 1948,
        "source_validation_evidence_id": "qrve_source",
    }

    row["status"] = "passed"
    with pytest.raises(RuntimeError, match="not an attestation-eligible failure"):
        validation.mirrored_welcome_attestation_context(
            "postgresql://runtime",
            job_id=94,
            release_sha="a" * 40,
            generation=17,
            policy_version="queue-v2-allowlisted",
        )


def test_upstream_welcome_delivery_attestation_reuses_exact_failed_context(
    monkeypatch,
    capsys,
) -> None:
    module = attest_queue_runtime_validation
    monkeypatch.setenv(module.AUTHORIZATION_ENV, "1")
    monkeypatch.setattr(module, "current_release_sha", lambda: "a" * 40)
    monkeypatch.setattr(module, "raw_database_url", lambda: "postgresql://runtime")
    monkeypatch.setattr(module, "normalize_runtime_database_url", lambda value: value)
    monkeypatch.setattr(
        module,
        "RuntimeGenerationRepository",
        lambda _url: SimpleNamespace(
            read_state=lambda: SimpleNamespace(
                active_generation=17,
                claim_enabled=True,
                policy_version="queue-v2-allowlisted",
                external_claim_scope="allowlisted",
            )
        ),
    )
    monkeypatch.setattr(module, "resolve_external_effect_job_id", lambda *_args, **_kwargs: 94)
    job = SimpleNamespace(
        id=94,
        execution_id="exe_mirrored_welcome",
        effect_type="wecom.welcome_message.send",
        side_effect_executed=True,
    )
    monkeypatch.setattr(
        module,
        "SQLAlchemyExternalEffectRepository",
        lambda: SimpleNamespace(
            get_job=lambda _job_id: job,
            list_attempts=lambda _job_id: [SimpleNamespace()],
        ),
    )
    monkeypatch.setattr(module, "wecom_canary_job_gate_error", lambda _job: "")
    context = {
        "source_webhook_inbox_id": 3810,
        "callback_duplicate_count": 0,
        "callback_to_provider_boundary_ms": 1948,
        "source_validation_evidence_id": "qrve_source",
    }
    monkeypatch.setattr(
        module,
        "mirrored_welcome_attestation_context",
        lambda *_args, **_kwargs: context,
    )
    recorded: dict = {}

    def record(_database_url, **kwargs):
        recorded.update(kwargs)
        return {
            "status": "passed",
            "side_effect_executed": True,
            "delivery_proof_mode": "upstream_operator_attested",
        }

    monkeypatch.setattr(module, "record_external_effect_evidence", record)

    assert (
        module.main(
            [
                "--execution-id",
                "exe_mirrored_welcome",
                "--job-id",
                "94",
                "--evidence-type",
                "wecom_welcome",
                "--expected-release-sha",
                "a" * 40,
                "--generation",
                "17",
                "--expected-policy-version",
                "queue-v2-allowlisted",
                "--actor",
                "github:qianlan333",
                "--reason",
                "operator observed production welcome delivery",
                "--upstream-welcome-delivery-attested",
                "--apply",
                "--confirmation",
                "ATTEST_QUEUE_EVIDENCE_exe_mirrored_welcome_17",
            ]
        )
        == 0
    )

    assert recorded["evidence_type"] == "wecom_welcome"
    assert recorded["extra_evidence"] == {
        **context,
        "upstream_welcome_delivery_attested": True,
        "upstream_welcome_attestation_kind": "operator_observed_delivery",
    }
    assert '"ok": true' in capsys.readouterr().out
