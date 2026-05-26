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

DOC = ROOT / "docs/development/phase_7e_fallback_cleanup_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_7e_fallback_cleanup_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7e_fallback_cleanup_readiness.py"
NEXT_BUNDLE = "phase_7f_production_compat_cleanup_readiness_bundle"
SELECTED_CANDIDATE = "task_groups_exact_route_fallback_cleanup_canary"
SELECTED_ROUTE = "/api/admin/automation-conversion/task-groups*"
FALSE_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
}
REQUIRED_EXCLUDED_FLAGS = {
    "payment",
    "oauth_callback",
    "wecom_callback",
    "timer_run_due",
    "outbound_send",
    "public_questionnaire_submit",
    "wildcard_fallback",
    "route_lacking_rollback_evidence",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7e_fallback_cleanup_readiness.md",
    "docs/development/phase_7e_fallback_cleanup_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7e_fallback_cleanup_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7e_fallback_cleanup_readiness.py",
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
    if data.get("bundle_type") != "phase_7e_fallback_cleanup_readiness_bundle":
        blockers.append("bundle_type must be phase_7e_fallback_cleanup_readiness_bundle")
    if data.get("cleanup_family") != "fallback_cleanup_readiness":
        blockers.append("cleanup_family must be fallback_cleanup_readiness")

    authorizations = _dict(data.get("authorizations"))
    for key in FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    inventory = _dict(data.get("fallback_inventory"))
    categories = _dict(inventory.get("categories"))
    exact_candidates = _list(categories.get("exact_route_fallback_candidates"))
    selected = [item for item in exact_candidates if isinstance(item, dict) and item.get("candidate_id") == SELECTED_CANDIDATE]
    if len(selected) != 1:
        blockers.append("exact_route_fallback_candidates must contain exactly one selected task-groups canary candidate")
    else:
        candidate = selected[0]
        if candidate.get("route_family") != SELECTED_ROUTE:
            blockers.append("selected fallback candidate route_family mismatch")
        for key in ("owner_approval_required", "behavior_change_expected_if_removed_later", "selected_for_phase_7g"):
            if candidate.get(key) is not True:
                blockers.append(f"selected fallback candidate {key} must be true")
        if candidate.get("fallback_removal_authorized") is not False:
            blockers.append("selected fallback candidate fallback_removal_authorized must be false in Phase 7E")
        required_evidence = {str(item) for item in _list(candidate.get("required_evidence"))}
        for required in ("owner_approval", "rollback_evidence", "shadow_compare_evidence", "route_ownership_proof"):
            if required not in required_evidence:
                blockers.append(f"selected fallback candidate missing required evidence: {required}")

    for category_name in (
        "docs_tooling_fallback_metadata_candidates",
        "production_compat_adjacent_candidates",
        "high_risk_deferred_fallback",
    ):
        if not _list(categories.get(category_name)):
            blockers.append(f"fallback inventory missing category: {category_name}")

    selected_cleanup = _dict(data.get("selected_first_fallback_cleanup_candidate"))
    if selected_cleanup.get("candidate_id") != SELECTED_CANDIDATE:
        blockers.append("selected_first_fallback_cleanup_candidate must choose task groups")
    if selected_cleanup.get("route_family") != SELECTED_ROUTE:
        blockers.append("selected_first_fallback_cleanup_candidate route mismatch")
    for key in (
        "fallback_removed_in_phase_7e",
        "production_behavior_changed",
        "production_compat_behavior_changed",
        "wildcard_fallback_touched",
        "runtime_deleted",
        "delete_ready",
    ):
        if selected_cleanup.get(key) is not False:
            blockers.append(f"selected_first_fallback_cleanup_candidate.{key} must be false")

    excluded = _dict(data.get("excluded_high_risk_fallback"))
    for key in sorted(REQUIRED_EXCLUDED_FLAGS):
        if excluded.get(key) is not True:
            blockers.append(f"excluded_high_risk_fallback.{key} must be true")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7F")

    if state.get("current_phase") != "phase_7e_fallback_cleanup_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 7E")
    if state.get("active_candidate") != "phase_7_fallback_cleanup_readiness":
        blockers.append("phase_execution_state.active_candidate must be phase_7_fallback_cleanup_readiness")
    if state.get("last_merged_pr") != "#778":
        blockers.append("phase_execution_state.last_merged_pr must record PR #778")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7F")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7F")
    phase_state = _dict(state.get("phase7e_fallback_cleanup_readiness"))
    if phase_state.get("selected_fallback_cleanup_candidate") != SELECTED_CANDIDATE:
        blockers.append("phase7e state must record selected task-groups fallback candidate")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"phase7e state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7E allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7E Fallback Cleanup Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
