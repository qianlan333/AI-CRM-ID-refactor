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

DOC = ROOT / "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6i_external_enablement_and_compat_readiness_acceptance.py"
ACCEPTANCE_STATUSES = {
    "accepted_for_owner_reviewed_enablement_tooling",
    "accepted_with_blocked_evidence_only",
    "needs_followup_before_enablement",
    "excluded_due_to_high_risk",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.md",
    "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6i_external_enablement_and_compat_readiness_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6i_external_enablement_and_compat_readiness_acceptance.py",
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
    for key in ("phase_6f_completed", "phase_6g_completed", "phase_6h_completed"):
        if _dict(data.get("completed_inventory")).get(key) is not True:
            blockers.append(f"completed_inventory.{key} must be true")
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    adapter_matrix = _list(data.get("external_adapter_enablement_matrix"))
    adapter_statuses = {str(item.get("acceptance_status")) for item in adapter_matrix if isinstance(item, dict)}
    if not {"accepted_for_owner_reviewed_enablement_tooling", "needs_followup_before_enablement", "excluded_due_to_high_risk"} <= adapter_statuses:
        blockers.append("external adapter matrix must include accepted, follow-up, and high-risk excluded statuses")
    for item in adapter_matrix:
        if not isinstance(item, dict):
            continue
        if item.get("acceptance_status") not in ACCEPTANCE_STATUSES:
            blockers.append(f"{item.get('family_key')}.acceptance_status is invalid")
        if item.get("fallback_retained") is not True:
            blockers.append(f"{item.get('family_key')}.fallback_retained must be true")
        if item.get("production_owner_switch") is not False:
            blockers.append(f"{item.get('family_key')}.production_owner_switch must be false")
        if item.get("live_external_call_by_default") is not False:
            blockers.append(f"{item.get('family_key')}.live_external_call_by_default must be false")

    compat_matrix = _list(data.get("production_compat_narrowing_readiness_matrix"))
    compat_statuses = {str(item.get("readiness_status")) for item in compat_matrix if isinstance(item, dict)}
    if not {"accepted_for_owner_reviewed_enablement_tooling", "accepted_with_blocked_evidence_only"} <= compat_statuses:
        blockers.append("production_compat matrix must include owner-reviewed and blocked-evidence readiness statuses")
    for item in compat_matrix:
        if not isinstance(item, dict):
            continue
        if item.get("production_compat_behavior_change") is not False:
            blockers.append(f"{item.get('exact_route')}.production_compat_behavior_change must be false")
        if item.get("fallback_retained") is not True:
            blockers.append(f"{item.get('exact_route')}.fallback_retained must be true")

    for key, value in _dict(data.get("acceptance_summary")).items():
        if value is not True:
            blockers.append(f"acceptance_summary.{key} must be true")
    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "phase_6j_timer_execution_readiness_bundle":
        blockers.append("next_bundle.recommended_next_step must recommend Phase 6J timer execution readiness")
    if next_bundle.get("fallback_next_step") != "phase_6j_low_risk_external_adapter_owner_reviewed_enablement_bundle":
        blockers.append("next_bundle.fallback_next_step must recommend low-risk external owner-reviewed enablement")
    if next_bundle.get("implement_6j_in_this_pr") is not False:
        blockers.append("next_bundle.implement_6j_in_this_pr must be false")

    if state.get("current_phase") != "phase_6i_external_enablement_and_compat_readiness_acceptance":
        blockers.append("phase_execution_state.current_phase must be Phase 6I")
    if state.get("active_candidate") != "external_enablement_and_compat_readiness_acceptance":
        blockers.append("phase_execution_state.active_candidate must be external_enablement_and_compat_readiness_acceptance")
    if state.get("last_merged_pr") != "#767":
        blockers.append("phase_execution_state.last_merged_pr must record PR #767")
    if state.get("recommended_next_pr") != "phase_6j_timer_execution_readiness_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6J timer execution readiness")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6I allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6I External Enablement And Compat Readiness Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
