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

DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py"
RUNNER = ROOT / "tools/run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py"
EXPECTED_STATUS = "post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence"
EXPECTED_BUNDLE = "post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence_bundle"
EXPECTED_ROUTE = "/api/admin/automation-conversion/task-groups*"
EXPECTED_MAIN_SHA = "2059090a473ec098acef9237212a40de8bab215f"
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
    "docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.md",
    "docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py",
    "tools/check_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py",
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
    for path in (DOC, PLAN_YAML, STATE, TEST, RUNNER):
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
    if data.get("cleanup_family") != "task_groups_shadow_compare_rollback_evidence":
        blockers.append("cleanup_family must be task_groups_shadow_compare_rollback_evidence")
    if data.get("route_family") != EXPECTED_ROUTE:
        blockers.append(f"route_family must be {EXPECTED_ROUTE}")

    authorizations = _dict(data.get("authorizations"))
    if authorizations.get("evidence_generation_authorized") is not True:
        blockers.append("authorizations.evidence_generation_authorized must be true")
    for key in REQUIRED_FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    if data.get("latest_main_sha") != EXPECTED_MAIN_SHA:
        blockers.append(f"latest_main_sha must be {EXPECTED_MAIN_SHA}")
    if "run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py" not in str(data.get("shadow_compare_command") or ""):
        blockers.append("shadow_compare_command must call the evidence runner")
    if data.get("shadow_compare_output_path") != "/tmp/task_groups_shadow_compare_evidence.json":
        blockers.append("shadow_compare_output_path must be /tmp/task_groups_shadow_compare_evidence.json")
    if data.get("shadow_compare_executed") is not True:
        blockers.append("shadow_compare_executed must be true")
    if data.get("shadow_compare_passed") is not True:
        blockers.append("shadow_compare_passed must be true")
    if not str(data.get("rollback_plan_path") or "").startswith("docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.md#rollback-plan"):
        blockers.append("rollback_plan_path must point to the bundle rollback plan")
    if "run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py" not in str(data.get("rollback_rehearsal_command") or ""):
        blockers.append("rollback_rehearsal_command must call the evidence runner")
    if data.get("rollback_rehearsal_output_path") != "/tmp/task_groups_rollback_rehearsal_evidence.json":
        blockers.append("rollback_rehearsal_output_path must be /tmp/task_groups_rollback_rehearsal_evidence.json")
    if data.get("rollback_rehearsal_executed") is not True:
        blockers.append("rollback_rehearsal_executed must be true")
    if data.get("rollback_rehearsal_passed") is not True:
        blockers.append("rollback_rehearsal_passed must be true")

    details_block = _dict(data.get("evidence_details"))
    for key in (
        "route_ownership_manifest_checked",
        "production_compat_exact_entry_checked",
        "native_route_entry_checked",
        "fixture_in_memory_probe_executed",
    ):
        if details_block.get(key) is not True:
            blockers.append(f"evidence_details.{key} must be true")
    for key in ("production_db_connected", "production_write_attempted", "wildcard_cleanup_required"):
        if details_block.get(key) is not False:
            blockers.append(f"evidence_details.{key} must be false")

    for key in (
        "production_behavior_changed",
        "fallback_removal_executed",
        "production_compat_cleanup_executed",
        "runtime_deletion_executed",
        "delete_ready",
    ):
        if data.get(key) is not False:
            blockers.append(f"{key} must be false")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("if_shadow_and_rollback_passed") != "post_phase7_cleanup_task_groups_owner_evidence_validation_bundle":
        blockers.append("next_bundle.if_shadow_and_rollback_passed must return to task-groups validation")
    if next_bundle.get("if_any_evidence_failed") != "post_phase7_cleanup_task_groups_shadow_rollback_blocker_acceptance_bundle":
        blockers.append("next_bundle.if_any_evidence_failed must point to blocker acceptance")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "task_groups_shadow_compare_rollback_evidence":
        blockers.append("phase_execution_state.active_candidate must be task_groups_shadow_compare_rollback_evidence")
    if state.get("last_merged_pr") != "#812":
        blockers.append("phase_execution_state.last_merged_pr must record #812")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_task_groups_owner_evidence_validation_bundle"}:
        blockers.append("phase_execution_state.next_allowed_actions must return to task-groups validation")
    phase_state = _dict(state.get("post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence"))
    if phase_state.get("status") != "post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence_completed":
        blockers.append("state shadow/rollback evidence status must be completed")
    if phase_state.get("shadow_compare_passed") is not True:
        blockers.append("state shadow_compare_passed must be true")
    if phase_state.get("rollback_rehearsal_passed") is not True:
        blockers.append("state rollback_rehearsal_passed must be true")
    for key in ("production_behavior_changed", "fallback_removed", "production_compat_cleanup_executed", "runtime_deletion_executed", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside task-groups shadow/rollback evidence allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Task-Groups Shadow Compare / Rollback Evidence Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
