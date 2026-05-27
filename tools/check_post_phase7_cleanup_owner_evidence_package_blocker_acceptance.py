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

DOC = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_blocker_acceptance.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_evidence_package_blocker_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_owner_evidence_package_blocker_acceptance.py"
EXPECTED_STATUS = "post_phase7_cleanup_owner_evidence_package_blocker_acceptance"
EXPECTED_BUNDLE = "post_phase7_cleanup_owner_evidence_package_blocker_acceptance_bundle"
EXPECTED_CLEANUP_FAMILY = "owner_evidence_package_blocker_acceptance"
REQUIRED_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_cleanup_authorized",
    "production_compat_behavior_change_authorized",
    "wildcard_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
    "exact_route_retry_authorized",
    "evidence_validation_authorized",
}
REQUIRED_MISSING_OWNER_EVIDENCE = {
    "route_specific_owner_approval",
    "rollback_owner",
    "workflow_nodes_rollback_execution_evidence",
    "risk_acceptance",
    "approval_timestamp",
}
REQUIRED_ROUTES = {
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/workflow-nodes*",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_owner_evidence_package_blocker_acceptance.md",
    "docs/development/post_phase7_cleanup_owner_evidence_package_blocker_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_owner_evidence_package_blocker_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_owner_evidence_package_blocker_acceptance.py",
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
    if data.get("cleanup_family") != EXPECTED_CLEANUP_FAMILY:
        blockers.append(f"cleanup_family must be {EXPECTED_CLEANUP_FAMILY}")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    source_prs = _dict(data.get("source_prs"))
    if source_prs.get("owner_evidence_waiting_acceptance") != 806:
        blockers.append("source_prs.owner_evidence_waiting_acceptance must be 806")
    if source_prs.get("owner_evidence_package_generation") != 807:
        blockers.append("source_prs.owner_evidence_package_generation must be 807")

    result = _dict(data.get("evidence_package_result"))
    if result.get("package_generated") is not True:
        blockers.append("evidence_package_result.package_generated must be true")
    if result.get("all_routes_blocked") is not True:
        blockers.append("evidence_package_result.all_routes_blocked must be true")
    if result.get("validation_authorized") is not False:
        blockers.append("evidence_package_result.validation_authorized must be false")
    if result.get("exact_route_cleanup_retry_authorized") is not False:
        blockers.append("evidence_package_result.exact_route_cleanup_retry_authorized must be false")

    missing_evidence = {str(item) for item in _list(data.get("missing_owner_only_evidence"))}
    missing_required = sorted(REQUIRED_MISSING_OWNER_EVIDENCE - missing_evidence)
    if missing_required:
        blockers.append(f"missing_owner_only_evidence missing: {missing_required}")

    blocked_routes = [_dict(item) for item in _list(data.get("blocked_routes"))]
    route_set = {str(item.get("route_family")) for item in blocked_routes}
    if route_set != REQUIRED_ROUTES:
        blockers.append(f"blocked_routes must be exactly {sorted(REQUIRED_ROUTES)}")
    for route in blocked_routes:
        route_family = str(route.get("route_family"))
        for key in (
            "ready_for_validation",
            "ready_for_exact_route_cleanup",
            "fallback_removal_executed",
            "production_compat_cleanup_executed",
            "runtime_deletion_executed",
        ):
            if route.get(key) is not False:
                blockers.append(f"{route_family}.{key} must be false")

    resume = _dict(data.get("resume_rules"))
    if resume.get("cleanup_track_status") != "blocked_waiting_owner_only_evidence":
        blockers.append("resume_rules.cleanup_track_status must be blocked_waiting_owner_only_evidence")
    if resume.get("next_allowed_action_without_owner_evidence") != "none":
        blockers.append("resume_rules.next_allowed_action_without_owner_evidence must be none")
    if resume.get("next_if_owner_evidence_complete") != "post_phase7_cleanup_owner_evidence_validation_bundle":
        blockers.append("resume_rules.next_if_owner_evidence_complete must be validation bundle")

    continuity = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "fallback_retained", "production_compat_retained", "legacy_runtime_retained"):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if continuity.get("delete_ready") is not False:
        blockers.append("business_continuity.delete_ready must be false")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "cleanup_owner_evidence_package_blocker_acceptance":
        blockers.append("phase_execution_state.active_candidate must be cleanup_owner_evidence_package_blocker_acceptance")
    if state.get("last_merged_pr") != "#807":
        blockers.append("phase_execution_state.last_merged_pr must record #807")
    if _list(state.get("next_allowed_actions")):
        blockers.append("phase_execution_state.next_allowed_actions must be empty while owner-only evidence is missing")
    phase_state = _dict(state.get("post_phase7_cleanup_owner_evidence_package_blocker_acceptance"))
    if phase_state.get("status") != "post_phase7_cleanup_owner_evidence_package_blocker_acceptance_completed":
        blockers.append("state package blocker acceptance status must be completed")
    if phase_state.get("cleanup_track_status") != "blocked_waiting_owner_only_evidence":
        blockers.append("state cleanup_track_status must be blocked_waiting_owner_only_evidence")
    if phase_state.get("all_routes_blocked") is not True:
        blockers.append("state all_routes_blocked must be true")
    if phase_state.get("evidence_validation_authorized") is not False:
        blockers.append("state evidence_validation_authorized must be false")
    if phase_state.get("exact_route_cleanup_retry_authorized") is not False:
        blockers.append("state exact_route_cleanup_retry_authorized must be false")
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
            blockers.append(f"state package blocker acceptance {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside owner evidence package blocker allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Cleanup Owner Evidence Package Blocker Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
