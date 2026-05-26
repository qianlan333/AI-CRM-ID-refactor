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

DOC = ROOT / "docs/development/phase_6b_task_groups_owner_switch_canary_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_6b_task_groups_owner_switch_canary_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6b_task_groups_owner_switch_canary_plan.py"

REQUIRED_TOP_LEVEL = {
    "route_family",
    "capability_owner",
    "current_owner",
    "proposed_owner",
    "owner_switch_execution_authorized",
    "fallback_retained",
    "production_compat_unchanged",
    "shadow_compare_required",
    "rollback_required",
    "timer_execution_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6b_task_groups_owner_switch_canary_plan.md",
    "docs/development/phase_6b_task_groups_owner_switch_canary_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6b_task_groups_owner_switch_canary_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6b_task_groups_owner_switch_canary_plan.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "nginx/",
    "systemd/",
)
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_DOC_CLAIMS = (
    "owner switch executed",
    "fallback removed",
    "production_compat changed",
    "timer enabled",
    "automation execution enabled",
    "outbound send enabled",
    "delete_ready true",
    "delete_ready: true",
)


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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
    details["route_family"] = data.get("route_family")
    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    if missing:
        blockers.append(f"YAML missing required fields: {missing}")

    expected_false = {
        "owner_switch_execution_authorized",
        "timer_execution_authorized",
        "automation_execution_authorized",
        "outbound_send_authorized",
        "delete_ready",
    }
    for key in expected_false:
        if data.get(key) is not False:
            blockers.append(f"{key} must be false")
    for key in ("fallback_retained", "production_compat_unchanged", "shadow_compare_required", "rollback_required"):
        if data.get(key) is not True:
            blockers.append(f"{key} must be true")

    if data.get("route_family") != "/api/admin/automation-conversion/task-groups*":
        blockers.append("route_family must be /api/admin/automation-conversion/task-groups*")
    if data.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")
    if data.get("proposed_owner") != "aicrm_next.automation_engine":
        blockers.append("proposed_owner must be aicrm_next.automation_engine")

    canary = _dict(data.get("canary_plan"))
    for key in ("exact_route_only", "owner_approval_required", "config_review_required", "rollback_owner_required"):
        if canary.get(key) is not True:
            blockers.append(f"canary_plan.{key} must be true")
    for key in ("default_owner_switch_allowed", "production_compat_behavior_change_allowed", "fallback_removal_allowed"):
        if canary.get(key) is not False:
            blockers.append(f"canary_plan.{key} must be false")

    shadow = _dict(data.get("shadow_compare_plan"))
    if shadow.get("required") is not True or shadow.get("default_blocked") is not True:
        blockers.append("shadow_compare_plan must be required and default_blocked")
    if not _list(shadow.get("required_evidence")):
        blockers.append("shadow_compare_plan.required_evidence must be non-empty")

    rollback = _dict(data.get("rollback_plan"))
    for key in ("required", "fallback_must_remain", "disable_canary_flag_restores_current_owner", "production_compat_unchanged"):
        if rollback.get(key) is not True:
            blockers.append(f"rollback_plan.{key} must be true")
    if rollback.get("destructive_migration_required") is not False:
        blockers.append("rollback_plan.destructive_migration_required must be false")
    if not _list(rollback.get("required_evidence")):
        blockers.append("rollback_plan.required_evidence must be non-empty")

    manifest = _dict(data.get("manifest_proposed_delta"))
    if manifest.get("proposed_only") is not True:
        blockers.append("manifest_proposed_delta.proposed_only must be true")
    if manifest.get("legacy_fallback_allowed") is not True:
        blockers.append("manifest_proposed_delta.legacy_fallback_allowed must be true")
    if manifest.get("production_compat_unchanged") is not True:
        blockers.append("manifest_proposed_delta.production_compat_unchanged must be true")
    if manifest.get("delete_ready") is not False:
        blockers.append("manifest_proposed_delta.delete_ready must be false")

    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "phase_6c_task_groups_owner_switch_tooling_bundle":
        blockers.append("next_bundle.recommended_next_step must point to Phase 6C")
    for key in ("owner_switch_execution_allowed", "production_compat_change_allowed", "fallback_removal_allowed"):
        if next_bundle.get(key) is not False:
            blockers.append(f"next_bundle.{key} must be false")

    if state.get("last_merged_pr") != "#758":
        blockers.append("phase_execution_state.last_merged_pr must record PR #758")
    if state.get("recommended_next_pr") != "phase_6c_task_groups_owner_switch_tooling_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6C")
    if _list(state.get("next_allowed_actions")) != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in FORBIDDEN_DOC_CLAIMS:
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6B allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6B Task Groups Owner Switch Canary Plan Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
