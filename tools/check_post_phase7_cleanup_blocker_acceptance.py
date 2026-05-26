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

DOC = ROOT / "docs/development/post_phase7_cleanup_blocker_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_blocker_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_blocker_acceptance.py"
REQUIRED_AUTHORIZATIONS = {
    "actual_fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "runtime_deletion_authorized",
    "wildcard_cleanup_authorized",
    "broad_fallback_removal_authorized",
    "delete_ready",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "payment_behavior_authorized",
    "oauth_callback_cutover_authorized",
    "wecom_callback_cutover_authorized",
    "public_submit_cutover_authorized",
}
REQUIRED_MISSING_EVIDENCE = {
    "owner_approval",
    "latest_main_shadow_compare",
    "rollback_owner",
    "rollback_plan",
    "rollback_execution_evidence",
    "route_ownership_proof",
    "production_compat_exact_entry_cleanup_proof",
}
REQUIRED_OWNER_ACTIONS = {
    "owner_approval",
    "latest_main_shadow_compare",
    "rollback_owner",
    "rollback_plan",
    "rollback_execution_evidence",
    "route_ownership_proof",
    "production_compat_exact_entry_proof",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_blocker_acceptance.md",
    "docs/development/post_phase7_cleanup_blocker_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_blocker_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_blocker_acceptance.py",
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
    if data.get("status") != "post_phase7_cleanup_blocker_acceptance":
        blockers.append("status must be post_phase7_cleanup_blocker_acceptance")
    if data.get("bundle_type") != "post_phase7_cleanup_blocker_acceptance_bundle":
        blockers.append("bundle_type must be post_phase7_cleanup_blocker_acceptance_bundle")
    if data.get("cleanup_family") != "owner_approved_cleanup_blocker_acceptance":
        blockers.append("cleanup_family must be owner_approved_cleanup_blocker_acceptance")
    if data.get("no_behavior_change") is not True:
        blockers.append("no_behavior_change must be true")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    blocked_routes = _list(data.get("blocked_route_families"))
    route_map = {str(item.get("route_family")): item for item in blocked_routes if isinstance(item, dict)}
    for route, source_pr in {
        "/api/admin/automation-conversion/task-groups*": 798,
        "/api/admin/automation-conversion/workflow-nodes*": 799,
    }.items():
        item = _dict(route_map.get(route))
        if item.get("source_pr") != source_pr:
            blockers.append(f"blocked_route_families {route} must reference source PR {source_pr}")
        if item.get("fallback_cleanup_status") != "blocked":
            blockers.append(f"{route} fallback_cleanup_status must be blocked")
        if item.get("production_compat_cleanup_status") != "blocked":
            blockers.append(f"{route} production_compat_cleanup_status must be blocked")
        missing_evidence = {str(value) for value in _list(item.get("missing_evidence"))}
        missing_required = sorted(REQUIRED_MISSING_EVIDENCE - missing_evidence)
        if missing_required:
            blockers.append(f"{route} missing_evidence missing: {missing_required}")

    owner_actions = {str(item) for item in _list(data.get("owner_action_list"))}
    missing_actions = sorted(REQUIRED_OWNER_ACTIONS - owner_actions)
    if missing_actions:
        blockers.append(f"owner_action_list missing: {missing_actions}")

    summary = _dict(data.get("cleanup_summary"))
    for key in ("fallback_removals_executed", "production_compat_cleanups_executed", "runtime_deletions_executed", "delete_ready_true_items"):
        if _list(summary.get(key)):
            blockers.append(f"cleanup_summary.{key} must be empty")
    for key in (
        "fallback_removal_occurred",
        "production_compat_behavior_changed",
        "runtime_deletion_occurred",
        "wildcard_cleanup_occurred",
        "delete_ready",
        "legacy_runtime_recheck_allowed",
    ):
        if summary.get(key) is not False:
            blockers.append(f"cleanup_summary.{key} must be false")
    if summary.get("legacy_runtime_recheck_blocked_reason") != "no_exact_route_cleanup_executed":
        blockers.append("cleanup_summary.legacy_runtime_recheck_blocked_reason must be no_exact_route_cleanup_executed")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "post_phase7_cleanup_owner_evidence_collection_bundle":
        blockers.append("next_bundle.recommended_next_step must be post_phase7_cleanup_owner_evidence_collection_bundle")

    if state.get("current_phase") != "post_phase7_cleanup_blocker_acceptance":
        blockers.append("phase_execution_state.current_phase must be cleanup blocker acceptance")
    if state.get("active_candidate") != "cleanup_blocker_acceptance":
        blockers.append("phase_execution_state.active_candidate must be cleanup_blocker_acceptance")
    if state.get("last_merged_pr") != "#799":
        blockers.append("phase_execution_state.last_merged_pr must record PR #799")
    if state.get("next_allowed_actions") != ["post_phase7_cleanup_owner_evidence_collection_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must only recommend owner evidence collection")
    phase_state = _dict(state.get("post_phase7_cleanup_blocker_acceptance"))
    if phase_state.get("status") != "post_phase7_cleanup_blocker_acceptance_completed":
        blockers.append("state cleanup blocker acceptance status must be completed")
    if phase_state.get("owner_evidence_collection_required") is not True:
        blockers.append("state must require owner evidence collection")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"state cleanup blocker acceptance {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside cleanup blocker acceptance allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Blocker Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
