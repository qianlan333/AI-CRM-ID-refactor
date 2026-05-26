#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_6k_single_scope_execution_canary_tooling.md"
PLAN_YAML = ROOT / "docs/development/phase_6k_single_scope_execution_canary_tooling.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6k_single_scope_execution_canary_tooling.py"
RUNNER = ROOT / "tools/run_phase6k_single_scope_execution_canary.py"
FALSE_KEYS = {
    "timer_execution_triggered",
    "run_due_execution_triggered",
    "automation_execution_triggered",
    "outbound_send_executed",
    "live_external_call_executed",
    "production_owner_changed",
    "production_compat_changed",
    "fallback_removed",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6k_single_scope_execution_canary_tooling.md",
    "docs/development/phase_6k_single_scope_execution_canary_tooling.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6k_single_scope_execution_canary_tooling.py",
    "tools/run_phase6k_single_scope_execution_canary.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6k_single_scope_execution_canary_tooling.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "docs/route_ownership/production_route_ownership_manifest.yaml"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _changed_files() -> set[str]:
    return set().union(
        _run_git(["diff", "--name-only", "origin/main...HEAD"]),
        _run_git(["diff", "--name-only"]),
        _run_git(["diff", "--name-only", "--cached"]),
        _run_git(["ls-files", "--others", "--exclude-standard"]),
    )


def _run_runner(args: list[str] | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(RUNNER.relative_to(ROOT)), *(args or [])],
        cwd=ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return {"_error": proc.stderr.strip() or proc.stdout.strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid json: {exc}"}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST, RUNNER):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("bundle_type") != "phase_6k_single_scope_execution_canary_tooling_bundle":
        blockers.append("bundle_type must be phase_6k_single_scope_execution_canary_tooling_bundle")
    if data.get("route_family") != "/api/admin/automation-conversion/workflow-nodes*":
        blockers.append("route_family must be workflow-nodes")
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    runner = _dict(data.get("runner"))
    for key in (
        "default_blocked",
        "single_scope_only",
        "dry_run_mode_supported",
        "shadow_run_mode_supported",
        "operator_identity_required",
        "idempotency_key_required",
        "audit_evidence_required",
        "pause_kill_switch_evidence_required",
        "rollback_cleanup_evidence_required",
    ):
        if runner.get(key) is not True:
            blockers.append(f"runner.{key} must be true")
    for key, value in _dict(data.get("guardrails")).items():
        if value is not True:
            blockers.append(f"guardrails.{key} must be true")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    defaults = _dict(data.get("default_runner_output"))
    if defaults.get("ok") is not True:
        blockers.append("default_runner_output.ok must be true")
    if not str(defaults.get("result_status", "")).startswith("not_executed_"):
        blockers.append("default_runner_output.result_status must be not_executed_*")
    for key in FALSE_KEYS:
        if defaults.get(key) is not False:
            blockers.append(f"default_runner_output.{key} must be false")
    if _list(data.get("next")) != ["phase_6l_phase6_aggregate_acceptance_bundle"]:
        blockers.append("next must only recommend Phase 6L")

    default_evidence = _run_runner()
    details["default_runner_evidence"] = default_evidence
    if default_evidence.get("ok") is not True:
        blockers.append("runner default ok must be true")
    if default_evidence.get("result_status") != "not_executed_missing_required_gates":
        blockers.append("runner default must be not_executed_missing_required_gates")
    if not default_evidence.get("missing_env_gates"):
        blockers.append("runner default must report missing env gates")
    for key in FALSE_KEYS:
        if default_evidence.get(key) is not False:
            blockers.append(f"runner default {key} must be false")

    full_env = {name: "1" for name in _list(data.get("required_env_gates"))}
    gate_ready_evidence = _run_runner(
        [
            "--dry-run",
            "--confirm-single-scope",
            "--confirm-no-outbound-send",
            "--confirm-no-live-external-call",
            "--confirm-kill-switch-ready",
            "--idempotency-key",
            "phase6k-test-key",
            "--operator",
            "phase6k-test-operator",
        ],
        env=full_env,
    )
    details["gate_ready_runner_evidence"] = gate_ready_evidence
    if gate_ready_evidence.get("result_status") != "not_executed_owner_reviewed_single_scope_gate_ready":
        blockers.append("runner with all gates must still be not_executed_owner_reviewed_single_scope_gate_ready")
    if gate_ready_evidence.get("kill_switch_ready") is not True:
        blockers.append("runner with all gates must report kill_switch_ready true")
    for key in FALSE_KEYS:
        if gate_ready_evidence.get(key) is not False:
            blockers.append(f"runner with all gates {key} must be false")

    if state.get("current_phase") != "phase_6k_single_scope_execution_canary_tooling":
        blockers.append("phase_execution_state.current_phase must be Phase 6K")
    if state.get("active_candidate") != "/api/admin/automation-conversion/workflow-nodes*":
        blockers.append("phase_execution_state.active_candidate must be workflow-nodes route family")
    if state.get("last_merged_pr") != "#770":
        blockers.append("phase_execution_state.last_merged_pr must record PR #770")
    if state.get("recommended_next_pr") != "phase_6l_phase6_aggregate_acceptance_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6L")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6K allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6K Single-Scope Execution Canary Tooling Check", "", f"- overall: {report['overall']}", "- blockers:"]
    lines.extend(f"  - {item}" for item in report.get("blockers", []) or ["none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

