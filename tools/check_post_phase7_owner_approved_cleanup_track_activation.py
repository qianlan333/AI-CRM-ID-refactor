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

DOC = ROOT / "docs/development/post_phase7_owner_approved_cleanup_track_activation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_owner_approved_cleanup_track_activation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_owner_approved_cleanup_track_activation.py"
REQUIRED_AUTHORIZATIONS = {
    "fallback_broad_removal_authorized",
    "production_compat_wildcard_cleanup_authorized",
    "legacy_runtime_deletion_authorized_by_default",
    "delete_ready",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "payment_behavior_authorized",
    "oauth_callback_cutover_authorized",
    "wecom_callback_cutover_authorized",
}
REQUIRED_CANDIDATES = {
    "task_groups_exact_route_fallback_cleanup",
    "task_groups_exact_route_production_compat_cleanup",
    "workflow_nodes_exact_route_fallback_cleanup",
    "workflow_nodes_exact_route_production_compat_cleanup",
    "dead_docs_checker_state_cleanup",
    "legacy_runtime_deletion_readiness_after_route_cleanup",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_owner_approved_cleanup_track_activation.md",
    "docs/development/post_phase7_owner_approved_cleanup_track_activation.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_owner_approved_cleanup_track_activation.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_owner_approved_cleanup_track_activation.py",
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
    if data.get("status") != "post_phase7_owner_approved_cleanup_track_activation":
        blockers.append("status must be post_phase7_owner_approved_cleanup_track_activation")
    if data.get("bundle_type") != "post_phase7_owner_approved_cleanup_track_activation_bundle":
        blockers.append("bundle_type must be post_phase7_owner_approved_cleanup_track_activation_bundle")
    if data.get("route_family") != "post_phase7_owner_approved_cleanup_track":
        blockers.append("route_family must be post_phase7_owner_approved_cleanup_track")
    if data.get("feature_selection_paused") is not True:
        blockers.append("feature_selection_paused must be true")
    if data.get("business_feature_implementation_authorized") is not False:
        blockers.append("business_feature_implementation_authorized must be false")
    if data.get("cleanup_track_authorized") is not True:
        blockers.append("cleanup_track_authorized must be true")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    handoff = _dict(data.get("phase_handoff"))
    for key in ("phase_7_final_acceptance_completed", "post_phase7a_rules_completed", "post_phase7b_intake_completed"):
        if handoff.get(key) is not True:
            blockers.append(f"phase_handoff.{key} must be true")
    if handoff.get("post_phase7b_selected_feature_status") != "pending_owner_selection":
        blockers.append("phase_handoff.post_phase7b_selected_feature_status must remain pending_owner_selection")
    if handoff.get("post_phase7b_implementation_authorized") is not False:
        blockers.append("phase_handoff.post_phase7b_implementation_authorized must be false")
    for key in ("fallback_retained", "production_compat_retained", "legacy_runtime_retained"):
        if handoff.get(key) is not True:
            blockers.append(f"phase_handoff.{key} must be true")
    if handoff.get("delete_ready") is not False:
        blockers.append("phase_handoff.delete_ready must be false")

    owner_request = _dict(data.get("owner_request"))
    for key in (
        "pause_new_feature_selection_path",
        "pause_hxc_feature_development",
        "pause_campaign_feature_development",
        "pause_material_picker_feature_development",
        "enter_owner_approved_cleanup_track",
    ):
        if owner_request.get(key) is not True:
            blockers.append(f"owner_request.{key} must be true")

    candidates = {str(item) for item in _list(data.get("first_cleanup_candidates"))}
    missing_candidates = sorted(REQUIRED_CANDIDATES - candidates)
    if missing_candidates:
        blockers.append(f"first_cleanup_candidates missing: {missing_candidates}")

    outcome = _dict(data.get("activation_outcome"))
    if outcome.get("cleanup_track_activated") is not True:
        blockers.append("activation_outcome.cleanup_track_activated must be true")
    for key in ("actual_fallback_removal", "actual_production_compat_change", "actual_runtime_deletion", "production_behavior_changed"):
        if outcome.get(key) is not False:
            blockers.append(f"activation_outcome.{key} must be false")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "post_phase7_cleanup_task_groups_evidence_refresh_bundle":
        blockers.append("next_bundle.recommended_next_step must be post_phase7_cleanup_task_groups_evidence_refresh_bundle")
    if next_bundle.get("route_family") != "/api/admin/automation-conversion/task-groups*":
        blockers.append("next_bundle.route_family must be task-groups")

    if state.get("current_phase") != "post_phase7_owner_approved_cleanup_track_activation":
        blockers.append("phase_execution_state.current_phase must be cleanup track activation")
    if state.get("active_candidate") != "post_phase7_owner_approved_cleanup_track":
        blockers.append("phase_execution_state.active_candidate must be owner approved cleanup track")
    if state.get("last_merged_pr") != "#796":
        blockers.append("phase_execution_state.last_merged_pr must record PR #796")
    if state.get("next_allowed_actions") != ["post_phase7_cleanup_task_groups_evidence_refresh_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must only recommend task-groups evidence refresh")
    phase_state = _dict(state.get("post_phase7_owner_approved_cleanup_track_activation"))
    if phase_state.get("cleanup_track_authorized") is not True:
        blockers.append("state cleanup_track_authorized must be true")
    for key in (
        "business_feature_implemented",
        "fallback_removed",
        "production_compat_behavior_changed",
        "production_compat_wildcard_cleanup",
        "legacy_runtime_deleted",
        "delete_ready",
        "timer_execution_enabled",
        "outbound_send_enabled",
    ):
        if phase_state.get(key) is not False:
            blockers.append(f"cleanup track activation state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside cleanup track activation allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Track Activation Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
