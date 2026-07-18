from __future__ import annotations

import pytest

from scripts.ops import authorize_wecom_canary_execution


def test_authorization_plan_binds_row_version_and_never_reads_runtime(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        authorize_wecom_canary_execution,
        "raw_database_url",
        lambda: pytest.fail("plan-only mode must not read the runtime database"),
    )

    assert (
        authorize_wecom_canary_execution.main(
            [
                "--execution-id",
                "exe_business_canary_001",
                "--expected-version",
                "7",
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
    assert '"expected_version": 7' in output
    assert '"target_values_redacted": true' in output
    assert '"real_external_call_executed": false' in output


def test_authorization_confirmation_binds_execution_and_expected_row_version() -> None:
    assert (
        authorize_wecom_canary_execution._confirmation("exe_business_canary_001", 7)
        == "AUTHORIZE_WECOM_CANARY_exe_business_canary_001_7"
    )
