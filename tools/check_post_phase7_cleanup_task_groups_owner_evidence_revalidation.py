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

DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_revalidation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_revalidation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_task_groups_owner_evidence_revalidation.py"
EXPECTED_STATUS = "post_phase7_cleanup_task_groups_owner_evidence_revalidation"
EXPECTED_BUNDLE = "post_phase7_cleanup_task_groups_owner_evidence_revalidation_bundle"
EXPECTED_ROUTE = "/api/admin/automation-conversion/task-groups*"
REQUIRED_SOURCE_PRS = {
    "waiting_acceptance": 806,
    "first_validation": 811,
    "blocker_acceptance": 812,
    "shadow_rollback_evidence": 813,
}
REQUIRED_FALSE_AUTHORIZATIONS = {
    "exact_route_cleanup_retry_authorized",
    "fallback_removal_authorized",
    "production_compat_cleanup_authorized",
    "production_compat_behavior_change_authorized",
    "wildcard_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
    "production_behavior_change_authorized",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_task_groups_owner_evidence_revalidation.md",
    "docs/development/post_phase7_cleanup_task_groups_owner_evidence_revalidation.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_task_groups_owner_evidence_revalidation.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_task_groups_owner_evidence_revalidation.py",
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
    if data.get("cleanup_family") != "task_groups_owner_evidence_revalidation":
        blockers.append("cleanup_family must be task_groups_owner_evidence_revalidation")
    if data.get("route_family") != EXPECTED_ROUTE:
        blockers.append(f"route_family must be {EXPECTED_ROUTE}")

    source_prs = _dict(data.get("source_prs"))
    for key, expected in REQUIRED_SOURCE_PRS.items():
        if source_prs.get(key) != expected:
            blockers.append(f"source_prs.{key} must be {expected}")

    authorizations = _dict(data.get("authorizations"))
    if authorizations.get("evidence_validation_authorized") is not True:
        blockers.append("authorizations.evidence_validation_authorized must be true")
    for key in REQUIRED_FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    owner = _dict(data.get("owner_evidence"))
    if _dict(owner.get("route_specific_owner_approval")).get("status") != "granted":
        blockers.append("owner route_specific_owner_approval.status must be granted")
    if _dict(owner.get("route_specific_owner_approval")).get("owner") != "qianlan":
        blockers.append("owner route_specific_owner_approval.owner must be qianlan")
    if _dict(owner.get("rollback_owner")).get("owner") != "qianlan":
        blockers.append("rollback owner must be qianlan")
    if _dict(owner.get("risk_acceptance")).get("status") != "granted_conditionally":
        blockers.append("risk_acceptance must be granted_conditionally")
    if _dict(owner.get("approval_timestamp")).get("status") != "recorded":
        blockers.append("approval_timestamp must be recorded")

    evidence = _dict(data.get("evidence_from_pr_813"))
    shadow = _dict(evidence.get("latest_main_shadow_compare"))
    if shadow.get("status") != "passed" or shadow.get("executed") is not True or shadow.get("passed") is not True:
        blockers.append("latest_main_shadow_compare must be executed and passed")
    if not shadow.get("output_path") or not shadow.get("latest_main_sha"):
        blockers.append("latest_main_shadow_compare must record output_path and latest_main_sha")
    if shadow.get("production_behavior_changed") is not False:
        blockers.append("latest_main_shadow_compare.production_behavior_changed must be false")
    rollback = _dict(evidence.get("rollback_rehearsal"))
    if rollback.get("status") != "passed" or rollback.get("executed") is not True or rollback.get("passed") is not True:
        blockers.append("rollback_rehearsal must be executed and passed")
    if not rollback.get("output_path"):
        blockers.append("rollback_rehearsal must record output_path")
    if rollback.get("production_behavior_changed") is not False:
        blockers.append("rollback_rehearsal.production_behavior_changed must be false")

    remaining = _dict(data.get("required_remaining_evidence"))
    route_proof = _dict(remaining.get("route_ownership_proof"))
    if route_proof.get("status") != "collected" or route_proof.get("proof_path") != "docs/route_ownership/production_route_ownership_manifest.yaml":
        blockers.append("route_ownership_proof must be collected from production_route_ownership_manifest.yaml")
    compat = _dict(remaining.get("production_compat_exact_entry_proof"))
    if compat.get("status") != "collected" or compat.get("exact_entry_found") is not True:
        blockers.append("production_compat_exact_entry_proof must be collected with exact_entry_found true")
    if compat.get("wildcard_cleanup_required") is not False:
        blockers.append("production_compat_exact_entry_proof.wildcard_cleanup_required must be false")

    result = _dict(data.get("validation_result"))
    for key in (
        "ready_for_exact_route_fallback_cleanup",
        "ready_for_exact_route_production_compat_cleanup",
        "ready_for_exact_route_cleanup_retry",
    ):
        if result.get(key) is not True:
            blockers.append(f"validation_result.{key} must be true")
    if _list(result.get("blocked_reason")):
        blockers.append("validation_result.blocked_reason must be empty when revalidation passes")

    continuity = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "fallback_retained", "production_compat_retained", "legacy_runtime_retained"):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if continuity.get("delete_ready") is not False:
        blockers.append("business_continuity.delete_ready must be false")

    cleanup = _dict(data.get("cleanup_execution"))
    for key in (
        "fallback_removal_executed",
        "production_compat_cleanup_executed",
        "production_compat_behavior_changed",
        "wildcard_cleanup_executed",
        "runtime_deletion_executed",
        "production_behavior_changed",
        "delete_ready",
    ):
        if cleanup.get(key) is not False:
            blockers.append(f"cleanup_execution.{key} must be false")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("if_ready") != "post_phase7_cleanup_task_groups_exact_route_retry_bundle":
        blockers.append("next_bundle.if_ready must be task-groups exact route retry")
    if next_bundle.get("if_blocked") != "post_phase7_cleanup_task_groups_owner_evidence_revalidation_blocker_acceptance_bundle":
        blockers.append("next_bundle.if_blocked must be revalidation blocker acceptance")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "task_groups_owner_evidence_revalidation":
        blockers.append("phase_execution_state.active_candidate must be task_groups_owner_evidence_revalidation")
    if state.get("last_merged_pr") != "#813":
        blockers.append("phase_execution_state.last_merged_pr must record #813")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_task_groups_exact_route_retry_bundle"}:
        blockers.append("phase_execution_state.next_allowed_actions must contain exact-route retry")
    phase_state = _dict(state.get("post_phase7_cleanup_task_groups_owner_evidence_revalidation"))
    if phase_state.get("status") != "post_phase7_cleanup_task_groups_owner_evidence_revalidation_completed":
        blockers.append("state task-groups revalidation status must be completed")
    if phase_state.get("ready_for_exact_route_cleanup_retry") is not True:
        blockers.append("state ready_for_exact_route_cleanup_retry must be true")
    for key in ("fallback_removed", "production_compat_cleanup_executed", "production_compat_behavior_changed", "runtime_deletion_executed", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside task-groups revalidation allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Task-Groups Owner Evidence Revalidation Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
