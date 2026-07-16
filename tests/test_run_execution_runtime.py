from __future__ import annotations

import pytest

from scripts import run_execution_runtime


def test_runtime_defaults_to_claimless_standby(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_QUEUE_RUNTIME_EXECUTE", raising=False)
    monkeypatch.delenv("AICRM_QUEUE_WORKER_GENERATION", raising=False)

    args = run_execution_runtime._parse_args(["--queue-kind", "internal"])

    assert args.execute is False
    assert args.generation == 0


def test_execute_requires_explicit_environment_gate(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_QUEUE_RUNTIME_EXECUTE", raising=False)

    with pytest.raises(SystemExit):
        run_execution_runtime._parse_args(["--queue-kind", "webhook", "--generation", "1", "--execute"])


def test_external_execute_is_test_only_until_canary_review(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUEUE_RUNTIME_EXECUTE", "1")

    with pytest.raises(SystemExit):
        run_execution_runtime._parse_args(["--queue-kind", "external", "--generation", "1", "--execute"])

    args = run_execution_runtime._parse_args(
        [
            "--queue-kind",
            "external",
            "--generation",
            "1",
            "--execute",
            "--test-only",
        ]
    )
    assert args.test_only is True
