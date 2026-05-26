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

DOC = ROOT / "docs/development/phase_7f_production_compat_cleanup_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_7f_production_compat_cleanup_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7f_production_compat_cleanup_readiness.py"
NEXT_BUNDLE = "phase_7g_first_exact_route_fallback_removal_canary_bundle"
SELECTED_CANDIDATE = "task_groups_exact_route_production_compat_cleanup_canary"
SELECTED_ROUTE = "/api/admin/automation-conversion/task-groups*"
FALSE_AUTHORIZATIONS = {
    "production_compat_behavior_change_authorized",
    "fallback_removal_authorized",
    "wildcard_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
}
REQUIRED_EXCLUDED_FLAGS = {
    "wildcard_production_compat",
    "payment",
    "oauth_callback",
    "wecom_callback",
    "timer_run_due",
    "outbound_send",
    "public_external_submit",
    "route_lacking_shadow_compare_or_rollback",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7f_production_compat_cleanup_readiness.md",
    "docs/development/phase_7f_production_compat_cleanup_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7f_production_compat_cleanup_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7f_production_compat_cleanup_readiness.py",
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
    if data.get("bundle_type") != "phase_7f_production_compat_cleanup_readiness_bundle":
        blockers.append("bundle_type must be phase_7f_production_compat_cleanup_readiness_bundle")
    if data.get("cleanup_family") != "production_compat_cleanup_readiness":
        blockers.append("cleanup_family must be production_compat_cleanup_readiness")

    authorizations = _dict(data.get("authorizations"))
    for key in FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    inventory = _dict(data.get("production_compat_inventory"))
    categories = _dict(inventory.get("categories"))
    exact_candidates = _list(categories.get("exact_route_cleanup_candidates"))
    selected = [item for item in exact_candidates if isinstance(item, dict) and item.get("candidate_id") == SELECTED_CANDIDATE]
    if len(selected) != 1:
        blockers.append("exact_route_cleanup_candidates must contain exactly one selected task-groups candidate")
    else:
        candidate = selected[0]
        if candidate.get("route_family") != SELECTED_ROUTE:
            blockers.append("selected production_compat candidate route_family mismatch")
        for key in ("owner_approval_required_before_behavior_change", "behavior_change_expected_if_removed_later", "selected_for_phase_7h"):
            if candidate.get(key) is not True:
                blockers.append(f"selected production_compat candidate {key} must be true")
        if candidate.get("production_compat_behavior_change_authorized") is not False:
            blockers.append("selected production_compat candidate behavior change authorization must be false")
        required_evidence = {str(item) for item in _list(candidate.get("required_evidence"))}
        for required in ("shadow_compare_evidence", "rollback_evidence", "route_ownership_proof", "fallback_status_known"):
            if required not in required_evidence:
                blockers.append(f"selected production_compat candidate missing required evidence: {required}")

    for category_name in (
        "route_ownership_manifest_proposed_delta",
        "docs_tooling_metadata_candidates",
        "wildcard_cleanup_excluded",
        "high_risk_deferred",
    ):
        if not _list(categories.get(category_name)):
            blockers.append(f"production_compat inventory missing category: {category_name}")

    selected_cleanup = _dict(data.get("selected_first_production_compat_cleanup_candidate"))
    if selected_cleanup.get("candidate_id") != SELECTED_CANDIDATE:
        blockers.append("selected_first_production_compat_cleanup_candidate must choose task groups")
    if selected_cleanup.get("route_family") != SELECTED_ROUTE:
        blockers.append("selected_first_production_compat_cleanup_candidate route mismatch")
    for key in (
        "production_compat_changed_in_phase_7f",
        "fallback_removed_in_phase_7f",
        "wildcard_cleanup_touched",
        "runtime_deleted",
        "delete_ready",
    ):
        if selected_cleanup.get(key) is not False:
            blockers.append(f"selected_first_production_compat_cleanup_candidate.{key} must be false")

    excluded = _dict(data.get("excluded_high_risk_production_compat"))
    for key in sorted(REQUIRED_EXCLUDED_FLAGS):
        if excluded.get(key) is not True:
            blockers.append(f"excluded_high_risk_production_compat.{key} must be true")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7G")

    if state.get("current_phase") != "phase_7f_production_compat_cleanup_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 7F")
    if state.get("active_candidate") != "phase_7_production_compat_cleanup_readiness":
        blockers.append("phase_execution_state.active_candidate must be phase_7_production_compat_cleanup_readiness")
    if state.get("last_merged_pr") != "#780":
        blockers.append("phase_execution_state.last_merged_pr must record PR #780")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7G")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7G")
    phase_state = _dict(state.get("phase7f_production_compat_cleanup_readiness"))
    if phase_state.get("selected_production_compat_cleanup_candidate") != SELECTED_CANDIDATE:
        blockers.append("phase7f state must record selected task-groups production_compat candidate")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"phase7f state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7F allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7F Production Compat Cleanup Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
