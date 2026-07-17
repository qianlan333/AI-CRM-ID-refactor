from __future__ import annotations

import pytest

from scripts.ops import run_queue_runtime_fault_drill


def test_fault_drill_plan_is_redacted_and_does_not_touch_systemd(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        run_queue_runtime_fault_drill,
        "_restart_service",
        lambda _service: pytest.fail("plan-only mode cannot restart a service"),
    )

    assert (
        run_queue_runtime_fault_drill.main(
            [
                "--action",
                "database_reconnect",
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
    assert '"claims_will_drain": true' in output
    assert '"target_values_redacted": true' in output


def test_fault_drill_systemd_restart_has_a_closed_service_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        run_queue_runtime_fault_drill.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("unsupported service must fail before systemctl"),
    )

    with pytest.raises(ValueError, match="outside the fault-drill allowlist"):
        run_queue_runtime_fault_drill._restart_service("openclaw-wecom-postgres.service")


def test_fault_drill_confirmation_binds_action_release_and_generation() -> None:
    assert run_queue_runtime_fault_drill._confirmation(
        "worker_restart",
        "a" * 40,
        17,
    ) == f"RUN_QUEUE_FAULT_WORKER_RESTART_{'a' * 40}_17"
