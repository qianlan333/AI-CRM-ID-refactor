#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4cu_internal_write_acceptance_review.md"
PLAN_YAML = ROOT / "docs/development/phase_4cu_internal_write_acceptance_review.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase4cu_internal_write_acceptance_review.py"
ROUTE_FAMILY = "phase_4_internal_write_aggregate"
NEXT_BUNDLE = "phase_4cv_phase5_readiness_entry_bundle"
NEXT_ROUTE_FAMILY = "phase_5_external_adapter_entry"
REQUIRED_ROUTE_FAMILIES = {
    "/api/admin/automation-conversion/profile-segment-templates*",
    "/api/admin/automation-conversion/action-templates*",
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/tasks*",
    "/api/admin/automation-conversion/workflows*",
    "/api/admin/automation-conversion/workflow-nodes*",
    "/api/admin/automation-conversion/agents*",
    "/api/admin/automation-conversion/agent-runs*",
    "/api/admin/automation-conversion/agent-outputs*",
}
REQUIRED_MATRIX_FIELDS = {
    "route_family",
    "capability_owner",
    "replacement_phase",
    "latest_phase_bundle",
    "has_fixture_native_contract",
    "has_repository_adapter",
    "has_local_or_test_parity",
    "has_staging_readiness",
    "has_production_readonly_dry_run_readiness",
    "production_owner_switched",
    "fallback_removed",
    "production_write_enabled",
    "phase_4_acceptance_status",
}
ALLOWED_ACCEPTANCE_STATUS = {
    "accepted_for_phase4_readiness",
    "awaiting_approval_or_config",
    "deferred_to_phase5_external_adapter",
    "deferred_to_phase6_execution_or_production_compat",
    "needs_followup_before_phase4_closure",
}
ALLOWED_CHANGED = {
    "docs/development/phase_4cu_internal_write_acceptance_review.md",
    "docs/development/phase_4cu_internal_write_acceptance_review.yaml",
    "tools/check_phase4cu_internal_write_acceptance_review.py",
    "tests/test_phase4cu_internal_write_acceptance_review.py",
    "docs/development/phase_execution_state.yaml",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"aicrm_next/main.py", "aicrm_next/production_compat/api.py", "app.py", "legacy_flask_app.py"}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        if str(ROOT) not in sys.path:
            sys.path[:0] = [str(ROOT)]
        from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml as fallback

        return fallback(path)


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, _ = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed, warnings


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("status") != "phase_4cu_internal_write_acceptance_review_no_runtime_change":
        blockers.append("status must be phase_4cu_internal_write_acceptance_review_no_runtime_change")
    if data.get("bundle_type") != "phase_4_internal_write_acceptance_review_bundle":
        blockers.append("bundle_type must be phase_4_internal_write_acceptance_review_bundle")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append("route_family must be phase_4_internal_write_aggregate")
    if data.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")

    authorizations = _dict_or_empty(data.get("authorizations"))
    if not authorizations:
        blockers.append("authorizations must be present")
    for key, value in sorted(authorizations.items()):
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    route_families = _list_or_empty(data.get("route_families"))
    route_family_names = {item.get("route_family") for item in route_families if isinstance(item, dict)}
    missing_route_families = sorted(REQUIRED_ROUTE_FAMILIES - route_family_names)
    if missing_route_families:
        blockers.append(f"route_families missing required entries: {missing_route_families}")
    for item in route_families:
        if not isinstance(item, dict):
            blockers.append("route_families entries must be mappings")
            continue
        route = item.get("route_family")
        if not item.get("latest_stage"):
            blockers.append(f"{route} missing latest_stage")
        status = item.get("phase_4_acceptance_status")
        if status not in ALLOWED_ACCEPTANCE_STATUS:
            blockers.append(f"{route} has invalid phase_4_acceptance_status: {status}")
        blockers_list = _list_or_empty(item.get("blockers"))
        if not blockers_list or not all(isinstance(blocker, dict) and blocker.get("item") for blocker in blockers_list):
            blockers.append(f"{route} must include blocker item entries")

    matrix = _dict_or_empty(data.get("acceptance_matrix"))
    if set(matrix.get("required_fields") or []) != REQUIRED_MATRIX_FIELDS:
        blockers.append("acceptance_matrix.required_fields must match the Phase 4CU contract")
    rows = _list_or_empty(matrix.get("rows"))
    row_routes = {row.get("route_family") for row in rows if isinstance(row, dict)}
    if not REQUIRED_ROUTE_FAMILIES <= row_routes:
        blockers.append("acceptance_matrix.rows must include all required route families")
    for row in rows:
        if not isinstance(row, dict):
            blockers.append("acceptance_matrix rows must be mappings")
            continue
        missing_fields = sorted(REQUIRED_MATRIX_FIELDS - set(row))
        if missing_fields:
            blockers.append(f"acceptance_matrix row {row.get('route_family')} missing fields: {missing_fields}")
        if row.get("phase_4_acceptance_status") not in ALLOWED_ACCEPTANCE_STATUS:
            blockers.append(f"acceptance_matrix row {row.get('route_family')} has invalid acceptance status")
        for field in ("production_owner_switched", "fallback_removed", "production_write_enabled"):
            if row.get(field) is not False:
                blockers.append(f"acceptance_matrix row {row.get('route_family')}.{field} must be false")

    decision = _dict_or_empty(data.get("phase_4_decision"))
    if not isinstance(decision.get("readiness_accepted"), bool):
        blockers.append("phase_4_decision.readiness_accepted must be boolean")
    for field in ("owner_switch_deferred", "fallback_removal_deferred", "production_compat_narrowing_deferred"):
        if decision.get(field) is not True:
            blockers.append(f"phase_4_decision.{field} must be true")

    phase5 = _dict_or_empty(data.get("phase_5_readiness"))
    if not isinstance(phase5.get("ready_for_phase5_planning"), bool):
        blockers.append("phase_5_readiness.ready_for_phase5_planning must be boolean")
    if phase5.get("external_live_calls_authorized") is not False:
        blockers.append("phase_5_readiness.external_live_calls_authorized must be false")
    if phase5.get("adapter_contract_first_required") is not True:
        blockers.append("phase_5_readiness.adapter_contract_first_required must be true")

    deferrals = _dict_or_empty(data.get("phase_6_7_deferral"))
    for field in (
        "production_owner_switch_deferred",
        "production_compat_narrowing_deferred",
        "fallback_removal_deferred",
        "timer_execution_deferred",
        "legacy_retirement_deferred",
    ):
        if deferrals.get(field) is not True:
            blockers.append(f"phase_6_7_deferral.{field} must be true")

    continuity = _dict_or_empty(data.get("business_continuity"))
    for field in (
        "production_behavior_unchanged",
        "legacy_fallback_retained",
        "fixture_local_demo_not_production_success",
        "blocked_evidence_not_success",
    ):
        if continuity.get(field) is not True:
            blockers.append(f"business_continuity.{field} must be true")

    next_bundle = _dict_or_empty(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE or next_bundle.get("route_family") != NEXT_ROUTE_FAMILY:
        blockers.append("next_bundle must point to phase_4cv_phase5_readiness_entry_bundle / phase_5_external_adapter_entry")

    if state.get("last_merged_pr") != "#709":
        blockers.append("phase state last_merged_pr must record #709")
    if state.get("last_attempted_action") != "phase_4cu_phase4_internal_write_acceptance_review":
        blockers.append("phase state last_attempted_action must be Phase 4CU")
    if state.get("last_created_pr") != "#710":
        blockers.append("phase state last_created_pr must be #710")
    if state.get("active_candidate") != NEXT_ROUTE_FAMILY:
        blockers.append("phase state active_candidate must advance to Phase 5 entry")
    if state.get("recommended_next_pr") != NEXT_BUNDLE or set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next action must advance to Phase 4CV Phase 5 readiness entry")
    if "phase_4cu_internal_write_acceptance_review_completed" not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4CU acceptance review")

    for phrase in (
        "production owner switched",
        "fallback removed",
        "production write enabled",
        "external calls enabled",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - ALLOWED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4CU: {unexpected}")
    protected = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if protected:
        blockers.append(f"forbidden no-runtime-change files changed: {protected}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "autopilot_deliverable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {"changed_files": sorted(changed), "bundle_type": data.get("bundle_type"), "route_family": data.get("route_family")},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CU Internal Write Acceptance Review Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Warnings",
            *(f"- {item}" for item in report["warnings"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
