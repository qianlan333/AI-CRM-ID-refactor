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


DOC = ROOT / "docs/development/post_phase7_cleanup_track_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_track_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_track_acceptance.py"
EXPECTED_STATUS = "post_phase7_cleanup_track_acceptance"
EXPECTED_BUNDLE = "post_phase7_cleanup_track_acceptance_bundle"
TASK_GROUPS_ROUTE = "/api/admin/automation-conversion/task-groups*"
WORKFLOW_NODES_ROUTE = "/api/admin/automation-conversion/workflow-nodes*"
TASK_GROUPS_CLEANUP_COMMIT = "809e6861c2fb9a344c312452d5ac22d131e293e8"
REQUIRED_SOURCE_PRS = {
    "owner_evidence_waiting": 806,
    "first_validation": 811,
    "validation_blocker_acceptance": 812,
    "shadow_rollback_evidence": 813,
    "revalidation": 814,
    "exact_route_cleanup_retry": 815,
    "legacy_runtime_recheck": 816,
}
REQUIRED_FALSE_AUTHORIZATIONS = {
    "further_cleanup_authorized_without_owner_evidence",
    "workflow_nodes_cleanup_authorized",
    "broad_fallback_removal_authorized",
    "wildcard_production_compat_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
}
REQUIRED_RUNTIME_BLOCKERS = {
    "workflow_nodes_fallback_retained",
    "workflow_nodes_production_compat_retained",
    "other_production_compat_routes_retained",
    "high_risk_external_runtime_retained",
    "manifest_and_tests_still_reference_retained_legacy_categories",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_track_acceptance.md",
    "docs/development/post_phase7_cleanup_track_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_track_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_track_acceptance.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}


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
    if data.get("status") != EXPECTED_STATUS:
        blockers.append(f"status must be {EXPECTED_STATUS}")
    if data.get("bundle_type") != EXPECTED_BUNDLE:
        blockers.append(f"bundle_type must be {EXPECTED_BUNDLE}")
    if data.get("cleanup_family") != "owner_approved_cleanup_track_acceptance":
        blockers.append("cleanup_family must be owner_approved_cleanup_track_acceptance")

    source_prs = _dict(data.get("source_prs"))
    for key, expected in REQUIRED_SOURCE_PRS.items():
        if source_prs.get(key) != expected:
            blockers.append(f"source_prs.{key} must be {expected}")

    cleanup = _dict(data.get("cleanup_results"))
    if TASK_GROUPS_ROUTE not in _list(cleanup.get("fallback_removals_executed")):
        blockers.append("cleanup_results.fallback_removals_executed must include task-groups")
    if TASK_GROUPS_ROUTE not in _list(cleanup.get("production_compat_cleanups_executed")):
        blockers.append("cleanup_results.production_compat_cleanups_executed must include task-groups")
    if cleanup.get("wildcard_cleanup_executed") is not False:
        blockers.append("cleanup_results.wildcard_cleanup_executed must be false")
    if _list(cleanup.get("runtime_deletions_executed")):
        blockers.append("cleanup_results.runtime_deletions_executed must be empty")
    if cleanup.get("delete_ready") is not False:
        blockers.append("cleanup_results.delete_ready must be false")

    rollback = _dict(data.get("rollback"))
    if rollback.get("available") is not True:
        blockers.append("rollback.available must be true")
    if rollback.get("rollback_method") != "revert_merge_commit":
        blockers.append("rollback.rollback_method must be revert_merge_commit")
    if rollback.get("rollback_commit") != TASK_GROUPS_CLEANUP_COMMIT:
        blockers.append("rollback.rollback_commit must be #815 merge commit")

    runtime_recheck = _dict(data.get("runtime_recheck"))
    if runtime_recheck.get("source_pr") != 816:
        blockers.append("runtime_recheck.source_pr must be 816")
    if runtime_recheck.get("safe_runtime_cleanup_candidate_selected") is not False:
        blockers.append("runtime_recheck.safe_runtime_cleanup_candidate_selected must be false")
    reasons = set(str(item) for item in _list(runtime_recheck.get("blocker_reasons")))
    if not reasons:
        blockers.append("runtime_recheck.blocker_reasons must not be empty")
    missing_reasons = sorted(REQUIRED_RUNTIME_BLOCKERS - reasons)
    if missing_reasons:
        blockers.append(f"runtime_recheck.blocker_reasons missing: {missing_reasons}")

    authorizations = _dict(data.get("authorizations"))
    for key in REQUIRED_FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    remaining = set(str(item) for item in _list(data.get("remaining_old_code_categories")))
    if not remaining:
        blockers.append("remaining_old_code_categories must not be empty")
    for key in ("workflow_nodes_fallback", "workflow_nodes_production_compat", "other_production_compat_route_families"):
        if key not in remaining:
            blockers.append(f"remaining_old_code_categories must include {key}")

    continuity = _dict(data.get("business_continuity"))
    if continuity.get("production_behavior_unchanged") is not True:
        blockers.append("business_continuity.production_behavior_unchanged must be true")
    if continuity.get("workflow_nodes_retained") is not True:
        blockers.append("business_continuity.workflow_nodes_retained must be true")
    if continuity.get("legacy_runtime_retained") is not True:
        blockers.append("business_continuity.legacy_runtime_retained must be true")
    if continuity.get("delete_ready") is not False:
        blockers.append("business_continuity.delete_ready must be false")

    next_actions = _dict(data.get("next_bundle"))
    if next_actions.get("if_owner_supplies_workflow_nodes_evidence") != "post_phase7_cleanup_workflow_nodes_owner_evidence_validation_bundle":
        blockers.append("next_bundle must point workflow-nodes evidence to validation")
    if next_actions.get("if_no_owner_evidence") != "paused_waiting_owner_evidence":
        blockers.append("next_bundle.if_no_owner_evidence must pause")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "owner_approved_cleanup_track_acceptance":
        blockers.append("phase_execution_state.active_candidate must be owner_approved_cleanup_track_acceptance")
    if state.get("last_merged_pr") != "#816":
        blockers.append("phase_execution_state.last_merged_pr must record #816")
    if set(_list(state.get("next_allowed_actions"))) != {"paused_waiting_owner_evidence"}:
        blockers.append("phase_execution_state.next_allowed_actions must pause without owner evidence")
    phase_state = _dict(state.get("post_phase7_cleanup_track_acceptance"))
    if phase_state.get("status") != "post_phase7_cleanup_track_acceptance_completed":
        blockers.append("state cleanup track acceptance status must be completed")
    if phase_state.get("task_groups_exact_route_cleanup_completed") is not True:
        blockers.append("state task_groups_exact_route_cleanup_completed must be true")
    if phase_state.get("workflow_nodes_cleanup_blocked") is not True:
        blockers.append("state workflow_nodes_cleanup_blocked must be true")
    if phase_state.get("runtime_deletion_blocked") is not True:
        blockers.append("state runtime_deletion_blocked must be true")
    if phase_state.get("delete_ready") is not False:
        blockers.append("state delete_ready must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside cleanup track acceptance allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Track Acceptance", "", f"- overall: {report['overall']}", "- blockers:"]
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
