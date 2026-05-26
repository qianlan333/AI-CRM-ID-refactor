#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_6l_phase6_aggregate_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_6l_phase6_aggregate_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6l_phase6_aggregate_acceptance.py"
REQUIRED_PHASES = {
    "phase_6a_owner_production_compat_readiness",
    "phase_6b_task_groups_owner_switch_canary_plan",
    "phase_6c_task_groups_owner_switch_tooling",
    "phase_6d_internal_metadata_owner_switch_batch",
    "phase_6e_internal_owner_switch_acceptance",
    "phase_6f_external_adapter_enablement_readiness",
    "phase_6g_low_risk_external_adapter_enablement_tooling",
    "phase_6h_production_compat_exact_route_narrowing_readiness",
    "phase_6i_external_enablement_and_compat_readiness_acceptance",
    "phase_6j_timer_execution_readiness",
    "phase_6k_single_scope_execution_canary_tooling",
}
FALSE_PRODUCTION_KEYS = {
    "production_owner_switches_executed",
    "production_compat_behavior_changed",
    "fallback_removed",
    "timer_execution_default_on",
    "run_due_execution_default_on",
    "automation_execution_default_on",
    "outbound_send",
    "live_external_default_on",
    "destructive_migration_executed",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6l_phase6_aggregate_acceptance.md",
    "docs/development/phase_6l_phase6_aggregate_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6l_phase6_aggregate_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6l_phase6_aggregate_acceptance.py",
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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("bundle_type") != "phase_6l_phase6_aggregate_acceptance_bundle":
        blockers.append("bundle_type must be phase_6l_phase6_aggregate_acceptance_bundle")
    if data.get("route_family") != "phase_6_aggregate_acceptance":
        blockers.append("route_family must be phase_6_aggregate_acceptance")
    completed = set(_list(data.get("phase_6_completed_inventory")))
    missing = sorted(REQUIRED_PHASES - completed)
    if missing:
        blockers.append(f"phase_6_completed_inventory missing {missing}")

    production = _dict(data.get("production_behavior_summary"))
    for key in FALSE_PRODUCTION_KEYS:
        if production.get(key) is not False:
            blockers.append(f"production_behavior_summary.{key} must be false")
    if production.get("production_owner_switch_executed_routes") != []:
        blockers.append("production_owner_switch_executed_routes must be empty")

    internal = _dict(data.get("internal_owner_switch_readiness"))
    if internal.get("production_owner_switch_executed") is not False:
        blockers.append("internal owner switch must not be executed")
    if internal.get("fallback_retained") is not True:
        blockers.append("internal fallback_retained must be true")
    if internal.get("production_compat_unchanged") is not True:
        blockers.append("internal production_compat_unchanged must be true")

    external = _dict(data.get("external_adapter_enablement_readiness"))
    if external.get("live_external_default_on") is not False:
        blockers.append("external live_external_default_on must be false")
    if external.get("outbound_send") is not False:
        blockers.append("external outbound_send must be false")

    compat = _dict(data.get("production_compat_exact_route_narrowing_readiness"))
    for key in ("production_compat_behavior_changed", "wildcard_narrowing_executed", "fallback_removed"):
        if compat.get(key) is not False:
            blockers.append(f"production_compat_exact_route_narrowing_readiness.{key} must be false")

    execution = _dict(data.get("execution_readiness_canary_tooling"))
    for key in ("timer_execution_actual", "run_due_execution_actual", "automation_execution_actual", "outbound_send_actual", "live_external_call_actual"):
        if execution.get(key) is not False:
            blockers.append(f"execution_readiness_canary_tooling.{key} must be false")
    if execution.get("default_blocked") is not True:
        blockers.append("execution canary tooling must remain default blocked")

    for key, value in _dict(data.get("phase_7_deferrals")).items():
        if value is not True:
            blockers.append(f"phase_7_deferrals.{key} must be true")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _list(data.get("next")) != ["phase_7a_legacy_retirement_readiness_bundle"]:
        blockers.append("next must only recommend Phase 7A")

    if state.get("current_phase") != "phase_6l_phase6_aggregate_acceptance":
        blockers.append("phase_execution_state.current_phase must be Phase 6L")
    if state.get("active_candidate") != "phase_6_aggregate_acceptance":
        blockers.append("phase_execution_state.active_candidate must be phase_6_aggregate_acceptance")
    if state.get("last_merged_pr") != "#772":
        blockers.append("phase_execution_state.last_merged_pr must record PR #772")
    if state.get("recommended_next_pr") != "phase_7a_legacy_retirement_readiness_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7A")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6L allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6L Aggregate Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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

