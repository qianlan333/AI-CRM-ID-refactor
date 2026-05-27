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

DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_generation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_generation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_owner_evidence_package_generation.py"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
EXPECTED_STATUS = "post_phase7_cleanup_owner_evidence_package_generation"
EXPECTED_BUNDLE = "post_phase7_cleanup_owner_evidence_package_generation_bundle"
EXPECTED_CLEANUP_FAMILY = "owner_evidence_package_generation"
EXPECTED_MAIN_SHA = "08f2a2255c389a244e1667fe92e9cb1431b135d8"
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
REQUIRED_ROUTES = {
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/workflow-nodes*",
}
REQUIRED_PACKAGE_FIELDS = {
    "route_family",
    "cleanup_candidate_id",
    "owner_approval",
    "latest_main_shadow_compare",
    "rollback_owner",
    "rollback_plan",
    "rollback_execution_evidence",
    "route_ownership_proof",
    "production_compat_exact_entry_proof",
    "risk_acceptance",
    "approval_timestamp",
    "ready_for_validation",
}
REQUIRED_OWNER_FIELDS = {"owner_approval", "rollback_owner", "risk_acceptance", "approval_timestamp"}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_owner_evidence_package_generation.md",
    "docs/development/post_phase7_cleanup_owner_evidence_package_generation.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_owner_evidence_package_generation.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_owner_evidence_package_generation.py",
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


def _validate_authorizations(data: dict[str, Any], blockers: list[str]) -> None:
    authorizations = _dict(data.get("authorizations"))
    missing = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing:
        blockers.append(f"authorizations missing: {missing}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")


def _validate_package(package: dict[str, Any], blockers: list[str]) -> None:
    route = str(package.get("route_family"))
    missing_fields = sorted(REQUIRED_PACKAGE_FIELDS - set(package))
    if missing_fields:
        blockers.append(f"{route} package missing fields: {missing_fields}")
    owner_approval = _dict(package.get("owner_approval"))
    if owner_approval.get("status") != "owner_required" or owner_approval.get("source") != "none":
        blockers.append(f"{route} owner_approval must remain owner_required with source none")
    shadow = _dict(package.get("latest_main_shadow_compare"))
    for field in ("status", "command", "output_path", "latest_main_sha", "production_behavior_changed"):
        if field not in shadow:
            blockers.append(f"{route} latest_main_shadow_compare missing {field}")
    if shadow.get("latest_main_sha") != EXPECTED_MAIN_SHA:
        blockers.append(f"{route} latest_main_shadow_compare.latest_main_sha must be {EXPECTED_MAIN_SHA}")
    if shadow.get("production_behavior_changed") is not False:
        blockers.append(f"{route} latest_main_shadow_compare.production_behavior_changed must be false")
    rollback_owner = _dict(package.get("rollback_owner"))
    if rollback_owner.get("status") != "owner_required":
        blockers.append(f"{route} rollback_owner.status must be owner_required")
    rollback_plan = _dict(package.get("rollback_plan"))
    if rollback_plan.get("status") != "draft_generated" or not rollback_plan.get("path"):
        blockers.append(f"{route} rollback_plan must point to a generated draft")
    rollback_evidence = _dict(package.get("rollback_execution_evidence"))
    for field in ("status", "command", "output_path", "production_behavior_changed"):
        if field not in rollback_evidence:
            blockers.append(f"{route} rollback_execution_evidence missing {field}")
    if rollback_evidence.get("production_behavior_changed") is not False:
        blockers.append(f"{route} rollback_execution_evidence.production_behavior_changed must be false")
    ownership = _dict(package.get("route_ownership_proof"))
    if ownership.get("status") != "collected" or ownership.get("source_manifest") != "docs/route_ownership/production_route_ownership_manifest.yaml":
        blockers.append(f"{route} route_ownership_proof must be collected from production_route_ownership_manifest.yaml")
    compat = _dict(package.get("production_compat_exact_entry_proof"))
    if compat.get("exact_entry_found") is not True:
        blockers.append(f"{route} production_compat_exact_entry_proof.exact_entry_found must be true")
    if compat.get("wildcard_cleanup_required") is not False:
        blockers.append(f"{route} production_compat_exact_entry_proof.wildcard_cleanup_required must be false")
    for field in ("risk_acceptance", "approval_timestamp"):
        if _dict(package.get(field)).get("status") != "owner_required":
            blockers.append(f"{route} {field}.status must be owner_required")
    if package.get("ready_for_validation") is not False:
        blockers.append(f"{route} ready_for_validation must remain false until owner fields are supplied")


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST, MANIFEST):
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
    if data.get("cleanup_family") != EXPECTED_CLEANUP_FAMILY:
        blockers.append(f"cleanup_family must be {EXPECTED_CLEANUP_FAMILY}")
    _validate_authorizations(data, blockers)

    baseline = _dict(data.get("source_baseline"))
    if baseline.get("latest_main_sha") != EXPECTED_MAIN_SHA:
        blockers.append(f"source_baseline.latest_main_sha must be {EXPECTED_MAIN_SHA}")
    for key, expected in {
        "waiting_acceptance_source_pr": 806,
        "owner_evidence_collection_source_pr": 802,
        "blocker_acceptance_source_pr": 801,
        "task_groups_evidence_refresh_source_pr": 798,
        "workflow_nodes_evidence_refresh_source_pr": 799,
    }.items():
        if baseline.get(key) != expected:
            blockers.append(f"source_baseline.{key} must be {expected}")

    packages = [_dict(item) for item in _list(data.get("evidence_packages"))]
    routes = {str(item.get("route_family")) for item in packages}
    if routes != REQUIRED_ROUTES:
        blockers.append(f"evidence_packages routes must be exactly {sorted(REQUIRED_ROUTES)}")
    for package in packages:
        _validate_package(package, blockers)

    owner_fields = {str(item) for item in _list(data.get("owner_required_fields"))}
    if not REQUIRED_OWNER_FIELDS <= owner_fields:
        blockers.append(f"owner_required_fields missing: {sorted(REQUIRED_OWNER_FIELDS - owner_fields)}")

    outcomes = _dict(data.get("outcomes"))
    if outcomes.get("task_groups_ready_for_validation") is not False:
        blockers.append("outcomes.task_groups_ready_for_validation must be false")
    if outcomes.get("workflow_nodes_ready_for_validation") is not False:
        blockers.append("outcomes.workflow_nodes_ready_for_validation must be false")
    if outcomes.get("all_blocked_owner_required") is not True:
        blockers.append("outcomes.all_blocked_owner_required must be true")
    for key in ("fallback_removals_executed", "production_compat_cleanups_executed", "runtime_deletions_executed"):
        if _list(outcomes.get(key)):
            blockers.append(f"outcomes.{key} must be empty")
    for key in (
        "production_behavior_changed",
        "production_compat_behavior_changed",
        "wildcard_cleanup_occurred",
        "runtime_deletion_executed",
        "delete_ready",
    ):
        if outcomes.get(key) is not False:
            blockers.append(f"outcomes.{key} must be false")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("if_any_evidence_package_ready") != "post_phase7_cleanup_owner_evidence_validation_bundle":
        blockers.append("next_bundle.if_any_evidence_package_ready must be validation bundle")
    if next_bundle.get("if_all_blocked") != "post_phase7_cleanup_owner_evidence_package_blocker_acceptance_bundle":
        blockers.append("next_bundle.if_all_blocked must be package blocker acceptance bundle")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "cleanup_owner_evidence_package_generation":
        blockers.append("phase_execution_state.active_candidate must be cleanup_owner_evidence_package_generation")
    if state.get("last_merged_pr") != "#806":
        blockers.append("phase_execution_state.last_merged_pr must record #806")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_owner_evidence_package_blocker_acceptance_bundle"}:
        blockers.append("phase_execution_state.next_allowed_actions must contain only package blocker acceptance")
    phase_state = _dict(state.get("post_phase7_cleanup_owner_evidence_package_generation"))
    if phase_state.get("status") != "post_phase7_cleanup_owner_evidence_package_generation_completed":
        blockers.append("state package generation status must be completed")
    if phase_state.get("all_blocked_owner_required") is not True:
        blockers.append("state package generation all_blocked_owner_required must be true")
    if phase_state.get("any_route_ready_for_validation") is not False:
        blockers.append("state package generation any_route_ready_for_validation must be false")
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
            blockers.append(f"state package generation {key} must be false")

    manifest_text = MANIFEST.read_text(encoding="utf-8")
    for route in REQUIRED_ROUTES:
        if f"route_pattern: {route}" not in manifest_text:
            blockers.append(f"manifest missing route proof for {route}")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside owner evidence package allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Owner Evidence Package Generation Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
