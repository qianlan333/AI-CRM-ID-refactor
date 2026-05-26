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

DOC = ROOT / "docs/development/post_phase7_cleanup_workflow_nodes_evidence_refresh.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_workflow_nodes_evidence_refresh.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_workflow_nodes_evidence_refresh.py"
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
REQUIRED_EVIDENCE_SOURCES = {
    "docs/development/phase_6d_internal_metadata_owner_switch_batch.yaml",
    "docs/development/phase_6e_internal_owner_switch_acceptance.yaml",
    "docs/development/phase_7e_fallback_cleanup_readiness.yaml",
    "docs/development/phase_7f_production_compat_cleanup_readiness.yaml",
    "docs/development/post_phase7_cleanup_task_groups_evidence_refresh.yaml",
    "docs/development/phase_execution_state.yaml",
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
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_workflow_nodes_evidence_refresh.md",
    "docs/development/post_phase7_cleanup_workflow_nodes_evidence_refresh.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_workflow_nodes_evidence_refresh.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_workflow_nodes_evidence_refresh.py",
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
    if data.get("status") != "post_phase7_cleanup_workflow_nodes_evidence_refresh":
        blockers.append("status must be post_phase7_cleanup_workflow_nodes_evidence_refresh")
    if data.get("bundle_type") != "post_phase7_cleanup_workflow_nodes_evidence_refresh_bundle":
        blockers.append("bundle_type must be post_phase7_cleanup_workflow_nodes_evidence_refresh_bundle")
    if data.get("route_family") != "/api/admin/automation-conversion/workflow-nodes*":
        blockers.append("route_family must be /api/admin/automation-conversion/workflow-nodes*")
    if data.get("cleanup_family") != "workflow_nodes_exact_route_cleanup_evidence_refresh":
        blockers.append("cleanup_family must be workflow_nodes_exact_route_cleanup_evidence_refresh")
    if data.get("no_behavior_change") is not True:
        blockers.append("no_behavior_change must be true")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    sources = {str(item) for item in _list(data.get("evidence_sources"))}
    missing_sources = sorted(REQUIRED_EVIDENCE_SOURCES - sources)
    if missing_sources:
        blockers.append(f"evidence_sources missing: {missing_sources}")

    evidence = _dict(data.get("evidence"))
    for key in (
        "phase6_owner_switch_tooling_accepted",
        "phase6e_internal_owner_switch_acceptance",
        "phase7e_fallback_readiness_exists",
        "phase7f_production_compat_readiness_exists",
        "task_groups_blocked_comparison_reviewed",
        "tests_cover_next_native_workflow_nodes_path",
        "no_outbound_send",
        "no_timer_execution",
        "no_external_live_call",
        "no_payment_or_oauth_or_wecom_callback",
        "no_public_submit_cutover",
    ):
        if evidence.get(key) is not True:
            blockers.append(f"evidence.{key} must be true")
    for key in (
        "route_ownership_proof",
        "owner_approval",
        "latest_main_shadow_compare",
        "rollback_owner",
        "rollback_plan",
        "rollback_execution_evidence",
        "production_compat_exact_entry_cleanup_proof",
    ):
        if evidence.get(key) != "missing":
            blockers.append(f"evidence.{key} must be missing")

    decision = _dict(data.get("decision"))
    if decision.get("ready_for_exact_route_fallback_cleanup") is not False:
        blockers.append("decision.ready_for_exact_route_fallback_cleanup must be false")
    if decision.get("ready_for_exact_route_production_compat_cleanup") is not False:
        blockers.append("decision.ready_for_exact_route_production_compat_cleanup must be false")
    if decision.get("blocked_with_missing_evidence") is not True:
        blockers.append("decision.blocked_with_missing_evidence must be true")
    missing_evidence = {str(item) for item in _list(decision.get("missing_evidence"))}
    missing_required = sorted(REQUIRED_MISSING_EVIDENCE - missing_evidence)
    if missing_required:
        blockers.append(f"decision.missing_evidence missing: {missing_required}")

    outcome = _dict(data.get("outcome"))
    if outcome.get("evidence_refresh_completed") is not True:
        blockers.append("outcome.evidence_refresh_completed must be true")
    for key in (
        "fallback_removal_executed",
        "production_compat_cleanup_executed",
        "runtime_deletion_executed",
        "production_behavior_changed",
        "production_compat_behavior_changed",
        "wildcard_cleanup_touched",
        "delete_ready",
    ):
        if outcome.get(key) is not False:
            blockers.append(f"outcome.{key} must be false")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "post_phase7_cleanup_blocker_acceptance_bundle":
        blockers.append("next_bundle.recommended_next_step must be post_phase7_cleanup_blocker_acceptance_bundle")

    if state.get("current_phase") != "post_phase7_cleanup_workflow_nodes_evidence_refresh":
        blockers.append("phase_execution_state.current_phase must be workflow-nodes evidence refresh")
    if state.get("active_candidate") != "workflow_nodes_cleanup_evidence_refresh":
        blockers.append("phase_execution_state.active_candidate must be workflow_nodes_cleanup_evidence_refresh")
    if state.get("last_merged_pr") != "#798":
        blockers.append("phase_execution_state.last_merged_pr must record PR #798")
    if state.get("next_allowed_actions") != ["post_phase7_cleanup_blocker_acceptance_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must only recommend cleanup blocker acceptance")
    phase_state = _dict(state.get("post_phase7_cleanup_workflow_nodes_evidence_refresh"))
    if phase_state.get("status") != "post_phase7_cleanup_workflow_nodes_evidence_refresh_completed":
        blockers.append("state workflow-nodes evidence refresh status must be completed")
    if phase_state.get("blocked_with_missing_evidence") is not True:
        blockers.append("state must record workflow-nodes blocked_with_missing_evidence true")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"state workflow-nodes evidence refresh {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside workflow-nodes evidence refresh allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Workflow-Nodes Cleanup Evidence Refresh Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
