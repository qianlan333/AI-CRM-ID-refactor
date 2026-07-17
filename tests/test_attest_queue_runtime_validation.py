from __future__ import annotations

from contextlib import nullcontext

import pytest

from aicrm_next.platform_foundation.execution_runtime import validation
from scripts.ops import attest_queue_runtime_validation


class _Rows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


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
