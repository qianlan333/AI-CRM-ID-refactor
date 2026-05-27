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

DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_task_groups_owner_evidence_validation.py"
EXPECTED_STATUS = "post_phase7_cleanup_task_groups_owner_evidence_validation"
EXPECTED_BUNDLE = "post_phase7_cleanup_task_groups_owner_evidence_validation_bundle"
EXPECTED_ROUTE = "/api/admin/automation-conversion/task-groups*"
EXPECTED_MAIN_SHA = "c9f3b3db97b1c3cbe8cbf6b28e2323c490a0009d"
REQUIRED_AUTHORIZATIONS = {
    "evidence_validation_authorized": True,
    "exact_route_cleanup_retry_authorized": False,
    "fallback_removal_authorized": False,
    "production_compat_cleanup_authorized": False,
    "production_compat_behavior_change_authorized": False,
    "wildcard_cleanup_authorized": False,
    "runtime_deletion_authorized": False,
    "delete_ready": False,
    "production_behavior_change_authorized": False,
}
REQUIRED_BLOCKED_REASONS = {
    "latest_main_shadow_compare_not_executed",
    "latest_main_shadow_compare_not_passed",
    "rollback_rehearsal_not_executed",
    "exact_route_cleanup_retry_not_authorized",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation.md",
    "docs/development/post_phase7_cleanup_task_groups_owner_evidence_validation.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_task_groups_owner_evidence_validation.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_task_groups_owner_evidence_validation.py",
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
    if data.get("cleanup_family") != "task_groups_owner_evidence_validation":
        blockers.append("cleanup_family must be task_groups_owner_evidence_validation")
    if data.get("route_family") != EXPECTED_ROUTE:
        blockers.append(f"route_family must be {EXPECTED_ROUTE}")

    authorizations = _dict(data.get("authorizations"))
    for key, expected in REQUIRED_AUTHORIZATIONS.items():
        if authorizations.get(key) is not expected:
            blockers.append(f"authorizations.{key} must be {str(expected).lower()}")

    owner = _dict(data.get("owner_evidence"))
    if _dict(owner.get("route_specific_owner_approval")).get("status") != "granted":
        blockers.append("owner route_specific_owner_approval must be granted")
    if _dict(owner.get("route_specific_owner_approval")).get("owner") != "qianlan":
        blockers.append("owner route_specific_owner_approval.owner must be qianlan")
    if _dict(owner.get("rollback_owner")).get("owner") != "qianlan":
        blockers.append("rollback owner must be qianlan")
    if _dict(owner.get("risk_acceptance")).get("status") != "granted_conditionally":
        blockers.append("risk_acceptance must be granted_conditionally")
    approval = _dict(owner.get("approval_timestamp"))
    if approval.get("status") != "recorded" or not approval.get("value"):
        blockers.append("approval_timestamp must be recorded with a value")

    fields = _dict(data.get("validation_fields"))
    shadow = _dict(fields.get("latest_main_shadow_compare"))
    if shadow.get("latest_main_sha") != EXPECTED_MAIN_SHA:
        blockers.append(f"latest_main_shadow_compare.latest_main_sha must be {EXPECTED_MAIN_SHA}")
    if shadow.get("production_behavior_changed") is not False:
        blockers.append("latest_main_shadow_compare.production_behavior_changed must be false")
    if shadow.get("shadow_compare_executed") is not False:
        blockers.append("latest_main_shadow_compare.shadow_compare_executed must remain false for blocked validation")
    if shadow.get("shadow_compare_passed") is not False:
        blockers.append("latest_main_shadow_compare.shadow_compare_passed must remain false for blocked validation")
    rollback_plan = _dict(fields.get("rollback_plan"))
    if rollback_plan.get("status") != "generated" or not rollback_plan.get("path"):
        blockers.append("rollback_plan must be generated with a path")
    rollback = _dict(fields.get("rollback_execution_evidence"))
    if rollback.get("rollback_executed") is not False:
        blockers.append("rollback_execution_evidence.rollback_executed must be false")
    if rollback.get("production_behavior_changed") is not False:
        blockers.append("rollback_execution_evidence.production_behavior_changed must be false")
    ownership = _dict(fields.get("route_ownership_proof"))
    if ownership.get("status") != "collected" or ownership.get("source_manifest") != "docs/route_ownership/production_route_ownership_manifest.yaml":
        blockers.append("route_ownership_proof must be collected from production_route_ownership_manifest.yaml")
    compat = _dict(fields.get("production_compat_exact_entry_proof"))
    if compat.get("exact_entry_found") is not True:
        blockers.append("production_compat_exact_entry_proof.exact_entry_found must be true")
    if compat.get("wildcard_cleanup_required") is not False:
        blockers.append("production_compat_exact_entry_proof.wildcard_cleanup_required must be false")

    result = _dict(data.get("validation_result"))
    for key in (
        "ready_for_exact_route_fallback_cleanup",
        "ready_for_exact_route_production_compat_cleanup",
        "ready_for_exact_route_cleanup_retry",
    ):
        if result.get(key) is not False:
            blockers.append(f"validation_result.{key} must be false")
    if result.get("validation_blocked") is not True:
        blockers.append("validation_result.validation_blocked must be true")
    reasons = {str(item) for item in _list(result.get("blocked_reason"))}
    missing_reasons = sorted(REQUIRED_BLOCKED_REASONS - reasons)
    if missing_reasons:
        blockers.append(f"validation_result.blocked_reason missing: {missing_reasons}")

    continuity = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "fallback_retained", "production_compat_retained", "legacy_runtime_retained"):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if continuity.get("delete_ready") is not False:
        blockers.append("business_continuity.delete_ready must be false")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "task_groups_owner_evidence_validation":
        blockers.append("phase_execution_state.active_candidate must be task_groups_owner_evidence_validation")
    if state.get("last_merged_pr") != "#810":
        blockers.append("phase_execution_state.last_merged_pr must record #810")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_task_groups_owner_evidence_validation_blocker_acceptance_bundle"}:
        blockers.append("phase_execution_state.next_allowed_actions must contain only validation blocker acceptance")
    phase_state = _dict(state.get("post_phase7_cleanup_task_groups_owner_evidence_validation"))
    if phase_state.get("status") != "post_phase7_cleanup_task_groups_owner_evidence_validation_completed":
        blockers.append("state task-groups validation status must be completed")
    if phase_state.get("validation_blocked") is not True:
        blockers.append("state validation_blocked must be true")
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
            blockers.append(f"state task-groups validation {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside task-groups validation allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Task-Groups Owner Evidence Validation Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
