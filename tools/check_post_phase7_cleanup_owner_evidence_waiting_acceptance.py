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

DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_owner_evidence_waiting_acceptance.py"
REQUIRED_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_cleanup_authorized",
    "production_compat_behavior_change_authorized",
    "wildcard_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
    "production_behavior_change_authorized",
    "exact_route_retry_authorized",
}
REQUIRED_SOURCE_PRS = {
    "task_groups_evidence_refresh": 798,
    "workflow_nodes_evidence_refresh": 799,
    "blocker_acceptance": 801,
    "owner_evidence_collection": 802,
}
REQUIRED_ROUTES = {
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/workflow-nodes*",
}
REQUIRED_EVIDENCE_FIELDS = {
    "route_family",
    "cleanup_type",
    "owner_approval",
    "latest_main_sha",
    "shadow_compare_command",
    "shadow_compare_output_path",
    "rollback_owner",
    "rollback_plan_path",
    "rollback_execution_command",
    "rollback_execution_output_path",
    "route_ownership_proof_path",
    "production_compat_exact_entry_proof_path",
    "risk_acceptance",
    "approval_timestamp",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.md",
    "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_owner_evidence_waiting_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_owner_evidence_waiting_acceptance.py",
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
    if data.get("status") != "post_phase7_cleanup_owner_evidence_waiting_acceptance":
        blockers.append("status must be post_phase7_cleanup_owner_evidence_waiting_acceptance")
    if data.get("bundle_type") != "post_phase7_cleanup_owner_evidence_waiting_acceptance_bundle":
        blockers.append("bundle_type must be post_phase7_cleanup_owner_evidence_waiting_acceptance_bundle")
    if data.get("cleanup_family") != "owner_evidence_waiting_acceptance":
        blockers.append("cleanup_family must be owner_evidence_waiting_acceptance")
    if data.get("no_behavior_change") is not True:
        blockers.append("no_behavior_change must be true")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    source_prs = _dict(data.get("source_prs"))
    for key, expected in REQUIRED_SOURCE_PRS.items():
        if source_prs.get(key) != expected:
            blockers.append(f"source_prs.{key} must be {expected}")

    blocked_routes = {str(item) for item in _list(data.get("blocked_routes"))}
    if blocked_routes != REQUIRED_ROUTES:
        blockers.append(f"blocked_routes must be exactly {sorted(REQUIRED_ROUTES)}")

    fields = {str(item) for item in _list(data.get("owner_evidence_package_required_fields"))}
    missing_fields = sorted(REQUIRED_EVIDENCE_FIELDS - fields)
    if missing_fields:
        blockers.append(f"owner_evidence_package_required_fields missing: {missing_fields}")

    outcome = _dict(data.get("cleanup_outcome"))
    if outcome.get("cleanup_track_status") != "paused_waiting_owner_evidence":
        blockers.append("cleanup_outcome.cleanup_track_status must be paused_waiting_owner_evidence")
    for key in ("fallback_removals_executed", "production_compat_cleanups_executed", "runtime_deletions_executed"):
        if _list(outcome.get(key)):
            blockers.append(f"cleanup_outcome.{key} must be empty")
    for key in (
        "fallback_removal_occurred",
        "production_compat_behavior_changed",
        "wildcard_cleanup_occurred",
        "runtime_deletion_occurred",
        "delete_ready",
    ):
        if outcome.get(key) is not False:
            blockers.append(f"cleanup_outcome.{key} must be false")

    resume = _dict(data.get("resume_rules"))
    if resume.get("cleanup_track_status") != "paused_waiting_owner_evidence":
        blockers.append("resume_rules.cleanup_track_status must be paused_waiting_owner_evidence")
    if resume.get("next_allowed_action_without_owner_evidence") != "none":
        blockers.append("resume_rules.next_allowed_action_without_owner_evidence must be none")
    if resume.get("next_if_evidence_complete") != "post_phase7_cleanup_exact_route_retry_bundle":
        blockers.append("resume_rules.next_if_evidence_complete must be post_phase7_cleanup_exact_route_retry_bundle")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("if_no_evidence_exists") != "stop_and_report_owner_evidence_waiting_blocker":
        blockers.append("next_bundle.if_no_evidence_exists must stop and report blocker")
    if next_bundle.get("if_evidence_exists") != "post_phase7_cleanup_owner_evidence_validation_bundle":
        blockers.append("next_bundle.if_evidence_exists must be post_phase7_cleanup_owner_evidence_validation_bundle")

    if state.get("current_phase") != "post_phase7_cleanup_owner_evidence_waiting_acceptance":
        blockers.append("phase_execution_state.current_phase must be owner evidence waiting acceptance")
    if state.get("active_candidate") != "cleanup_owner_evidence_waiting_acceptance":
        blockers.append("phase_execution_state.active_candidate must be cleanup_owner_evidence_waiting_acceptance")
    if state.get("last_merged_pr") != "#802":
        blockers.append("phase_execution_state.last_merged_pr must record cleanup PR #802")
    if _list(state.get("next_allowed_actions")):
        blockers.append("phase_execution_state.next_allowed_actions must be empty while waiting for owner evidence")
    phase_state = _dict(state.get("post_phase7_cleanup_owner_evidence_waiting_acceptance"))
    if phase_state.get("status") != "post_phase7_cleanup_owner_evidence_waiting_acceptance_completed":
        blockers.append("state owner evidence waiting acceptance status must be completed")
    if phase_state.get("cleanup_track_status") != "paused_waiting_owner_evidence":
        blockers.append("state cleanup_track_status must be paused_waiting_owner_evidence")
    if phase_state.get("next_allowed_action_without_owner_evidence") != "none":
        blockers.append("state next_allowed_action_without_owner_evidence must be none")
    for key in (
        "fallback_removed",
        "production_compat_behavior_changed",
        "production_compat_cleanup_executed",
        "wildcard_cleanup",
        "legacy_runtime_deleted",
        "runtime_deletion_executed",
        "delete_ready",
    ):
        if phase_state.get(key) is not False:
            blockers.append(f"state owner evidence waiting acceptance {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside owner evidence waiting acceptance allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Owner Evidence Waiting Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
