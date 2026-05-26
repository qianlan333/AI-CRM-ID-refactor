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

DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_collection.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_collection.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_owner_evidence_collection.py"
REQUIRED_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_cleanup_authorized",
    "production_compat_behavior_change_authorized",
    "wildcard_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
    "production_behavior_change_authorized",
}
REQUIRED_SOURCE_BLOCKERS = {
    "task_groups_source_pr": 798,
    "workflow_nodes_source_pr": 799,
    "blocker_acceptance_source_pr": 801,
}
REQUIRED_ROUTES = {
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/workflow-nodes*",
}
REQUIRED_EVIDENCE_FIELDS = {
    "owner_approval_status",
    "latest_main_shadow_compare_status",
    "rollback_owner_status",
    "rollback_plan_status",
    "rollback_execution_evidence_status",
    "route_ownership_proof_status",
    "production_compat_exact_entry_proof_status",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_owner_evidence_collection.md",
    "docs/development/post_phase7_cleanup_owner_evidence_collection.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_owner_evidence_collection.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_owner_evidence_collection.py",
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
    if data.get("status") != "post_phase7_cleanup_owner_evidence_collection":
        blockers.append("status must be post_phase7_cleanup_owner_evidence_collection")
    if data.get("bundle_type") != "post_phase7_cleanup_owner_evidence_collection_bundle":
        blockers.append("bundle_type must be post_phase7_cleanup_owner_evidence_collection_bundle")
    if data.get("cleanup_family") != "owner_evidence_collection":
        blockers.append("cleanup_family must be owner_evidence_collection")
    if data.get("no_behavior_change") is not True:
        blockers.append("no_behavior_change must be true")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    source_blockers = _dict(data.get("source_blockers"))
    for key, expected in REQUIRED_SOURCE_BLOCKERS.items():
        if source_blockers.get(key) != expected:
            blockers.append(f"source_blockers.{key} must be {expected}")

    matrix = _list(data.get("evidence_matrix"))
    route_map = {str(item.get("route_family")): item for item in matrix if isinstance(item, dict)}
    missing_routes = sorted(REQUIRED_ROUTES - set(route_map))
    if missing_routes:
        blockers.append(f"evidence_matrix missing routes: {missing_routes}")
    for route in sorted(REQUIRED_ROUTES):
        item = _dict(route_map.get(route))
        missing_fields = sorted(REQUIRED_EVIDENCE_FIELDS - set(item))
        if missing_fields:
            blockers.append(f"{route} evidence fields missing: {missing_fields}")
        for field in REQUIRED_EVIDENCE_FIELDS:
            if item.get(field) != "missing":
                blockers.append(f"{route} {field} must be missing")
        if item.get("ready_for_fallback_cleanup") is not False:
            blockers.append(f"{route} ready_for_fallback_cleanup must be false")
        if item.get("ready_for_production_compat_cleanup") is not False:
            blockers.append(f"{route} ready_for_production_compat_cleanup must be false")
        if not item.get("blocked_reason"):
            blockers.append(f"{route} blocked_reason must be present")
        if not item.get("next_owner_action"):
            blockers.append(f"{route} next_owner_action must be present")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("if_any_route_ready") != "post_phase7_cleanup_exact_route_retry_bundle":
        blockers.append("next_bundle.if_any_route_ready must be post_phase7_cleanup_exact_route_retry_bundle")
    if next_bundle.get("if_all_routes_blocked") != "post_phase7_cleanup_owner_evidence_waiting_acceptance_bundle":
        blockers.append("next_bundle.if_all_routes_blocked must be post_phase7_cleanup_owner_evidence_waiting_acceptance_bundle")

    if state.get("current_phase") != "post_phase7_cleanup_owner_evidence_collection":
        blockers.append("phase_execution_state.current_phase must be owner evidence collection")
    if state.get("active_candidate") != "cleanup_owner_evidence_collection":
        blockers.append("phase_execution_state.active_candidate must be cleanup_owner_evidence_collection")
    if state.get("last_merged_pr") != "#801":
        blockers.append("phase_execution_state.last_merged_pr must record PR #801")
    if state.get("next_allowed_actions") != ["post_phase7_cleanup_owner_evidence_waiting_acceptance_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must only recommend owner evidence waiting acceptance")
    phase_state = _dict(state.get("post_phase7_cleanup_owner_evidence_collection"))
    if phase_state.get("status") != "post_phase7_cleanup_owner_evidence_collection_completed":
        blockers.append("state owner evidence collection status must be completed")
    if phase_state.get("routes_all_blocked") is not True:
        blockers.append("state owner evidence collection routes_all_blocked must be true")
    if phase_state.get("any_route_ready") is not False:
        blockers.append("state owner evidence collection any_route_ready must be false")
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
            blockers.append(f"state owner evidence collection {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside owner evidence collection allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Owner Evidence Collection Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
