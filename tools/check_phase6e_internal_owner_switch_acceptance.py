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

DOC = ROOT / "docs/development/phase_6e_internal_owner_switch_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_6e_internal_owner_switch_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6e_internal_owner_switch_acceptance.py"
ACCEPTANCE_STATUSES = {
    "accepted_for_owner_switch_canary_tooling",
    "accepted_with_blocked_evidence_only",
    "needs_followup_before_owner_switch",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6e_internal_owner_switch_acceptance.md",
    "docs/development/phase_6e_internal_owner_switch_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6e_internal_owner_switch_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6e_internal_owner_switch_acceptance.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}


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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
    inventory = _dict(data.get("completed_inventory"))
    for key in ("phase_6b_completed", "phase_6c_completed", "phase_6d_completed"):
        if inventory.get(key) is not True:
            blockers.append(f"completed_inventory.{key} must be true")

    matrix = _list(data.get("route_family_matrix"))
    statuses = {str(item.get("acceptance_status")) for item in matrix if isinstance(item, dict)}
    if not ACCEPTANCE_STATUSES <= statuses:
        blockers.append("route_family_matrix must include all required acceptance statuses")
    for item in matrix:
        if not isinstance(item, dict):
            continue
        if item.get("production_compat_unchanged") is not True:
            blockers.append(f"{item.get('route_family')}.production_compat_unchanged must be true")
        if item.get("fallback_retained") is not True:
            blockers.append(f"{item.get('route_family')}.fallback_retained must be true")
        if item.get("acceptance_status") not in ACCEPTANCE_STATUSES:
            blockers.append(f"{item.get('route_family')}.acceptance_status is invalid")

    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    for key, value in _dict(data.get("acceptance_summary")).items():
        if value is not True:
            blockers.append(f"acceptance_summary.{key} must be true")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "phase_6f_external_adapter_enablement_readiness_bundle":
        blockers.append("next_bundle.recommended_next_step must point to external adapter enablement readiness")
    if next_bundle.get("fallback_next_step") != "phase_6f_internal_owner_switch_followup_bundle":
        blockers.append("next_bundle.fallback_next_step must point to internal owner switch followup")
    for key in ("owner_switch_execution_allowed_default", "production_compat_change_allowed", "fallback_removal_allowed"):
        if next_bundle.get(key) is not False:
            blockers.append(f"next_bundle.{key} must be false")

    if state.get("last_merged_pr") != "#762":
        blockers.append("phase_execution_state.last_merged_pr must record PR #762")
    if state.get("recommended_next_pr") != "phase_6f_external_adapter_enablement_readiness_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6F external adapter readiness")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6E allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6E Internal Owner Switch Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
