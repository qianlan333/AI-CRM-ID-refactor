from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import tools.check_phase6k_single_scope_execution_canary_tooling as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6k_single_scope_execution_canary_tooling.yaml"
RUNNER = ROOT / "tools/run_phase6k_single_scope_execution_canary.py"


def _run(args: list[str] | None = None, env: dict[str, str] | None = None) -> dict[str, object]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(RUNNER.relative_to(ROOT)), *(args or [])],
        cwd=ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    return json.loads(proc.stdout)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_default_runner_blocked_and_side_effect_free() -> None:
    evidence = _run()
    assert evidence["ok"] is True
    assert evidence["result_status"] == "not_executed_missing_required_gates"
    assert evidence["missing_env_gates"]
    for key in checker.FALSE_KEYS:
        assert evidence[key] is False


def test_runner_with_all_gates_still_does_not_execute() -> None:
    env = {name: "1" for name in checker.load_yaml(PLAN_YAML)["required_env_gates"]}
    evidence = _run(
        [
            "--shadow-run",
            "--confirm-single-scope",
            "--confirm-no-outbound-send",
            "--confirm-no-live-external-call",
            "--confirm-kill-switch-ready",
            "--idempotency-key",
            "test-key",
            "--operator",
            "test-operator",
        ],
        env=env,
    )
    assert evidence["result_status"] == "not_executed_owner_reviewed_single_scope_gate_ready"
    assert evidence["kill_switch_ready"] is True
    assert evidence["audit_evidence"]["operator"] == "test-operator"
    assert evidence["audit_evidence"]["idempotency_key_provided"] is True
    for key in checker.FALSE_KEYS:
        assert evidence[key] is False


def test_business_continuity_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["business_continuity"].values())
    assert data["next"] == ["phase_6l_phase6_aggregate_acceptance_bundle"]

