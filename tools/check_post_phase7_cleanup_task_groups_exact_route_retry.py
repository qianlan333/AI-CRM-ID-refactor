#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml


DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_exact_route_retry.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_exact_route_retry.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
NATIVE_API = ROOT / "aicrm_next/automation_engine/api.py"
TEST = ROOT / "tests/test_post_phase7_cleanup_task_groups_exact_route_retry.py"
EXPECTED_STATUS = "post_phase7_cleanup_task_groups_exact_route_retry"
EXPECTED_BUNDLE = "post_phase7_cleanup_task_groups_exact_route_retry_bundle"
EXPECTED_ROUTE = "/api/admin/automation-conversion/task-groups*"
TASK_GROUPS_EXACT = "/api/admin/automation-conversion/task-groups"
REQUIRED_SOURCE_PRS = {
    "owner_evidence_waiting": 806,
    "first_validation": 811,
    "blocker_acceptance": 812,
    "shadow_rollback_evidence": 813,
    "revalidation": 814,
}
REQUIRED_FALSE_AUTHORIZATIONS = {
    "broad_fallback_removal_authorized",
    "wildcard_production_compat_cleanup_authorized",
    "runtime_deletion_authorized",
    "delete_ready",
    "payment_oauth_wecom_callback_timer_outbound_affected",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/production_compat/api.py",
    "docs/route_ownership/production_route_ownership_manifest.yaml",
    "docs/development/legacy_replacement_backlog.md",
    "docs/development/legacy_replacement_backlog.yaml",
    "docs/development/post_phase7_cleanup_task_groups_exact_route_retry.md",
    "docs/development/post_phase7_cleanup_task_groups_exact_route_retry.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_task_groups_exact_route_retry.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/check_legacy_facade_growth_freeze.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_task_groups_exact_route_retry.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = (
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "nginx/",
    "systemd/",
)
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}
EXPECTED_REMOVED_COMPAT_LINES = {
    f'@router.api_route("{TASK_GROUPS_EXACT}", methods=_ALL_METHODS)',
    f'@router.api_route("{TASK_GROUPS_EXACT}/{{path:path}}", methods=_ALL_METHODS)',
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _git_text(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def _changed_files() -> set[str]:
    return set().union(
        _run_git(["diff", "--name-only", "origin/main...HEAD"]),
        _run_git(["diff", "--name-only"]),
        _run_git(["diff", "--name-only", "--cached"]),
        _run_git(["ls-files", "--others", "--exclude-standard"]),
    )


def _route_manifest_entry() -> dict[str, Any]:
    data = load_yaml(MANIFEST)
    for entry in _list(data.get("routes")):
        if isinstance(entry, dict) and entry.get("route_pattern") == EXPECTED_ROUTE:
            return entry
    return {}


def _contains_decorator(text: str, route: str) -> bool:
    return f'"{route}"' in text or f"'{route}'" in text


def _production_compat_diff_is_scoped() -> bool:
    diff = "\n".join(
        part
        for part in (
            _git_text(["diff", "origin/main...HEAD", "--", "aicrm_next/production_compat/api.py"]),
            _git_text(["diff", "--", "aicrm_next/production_compat/api.py"]),
            _git_text(["diff", "--cached", "--", "aicrm_next/production_compat/api.py"]),
        )
        if part
    )
    changed_lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            changed_lines.append(line)
    return set(changed_lines) == {f"-{line}" for line in EXPECTED_REMOVED_COMPAT_LINES}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, MANIFEST, PRODUCTION_COMPAT, NATIVE_API, TEST):
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
    if data.get("cleanup_family") != "task_groups_exact_route_cleanup_retry":
        blockers.append("cleanup_family must be task_groups_exact_route_cleanup_retry")
    if data.get("route_family") != EXPECTED_ROUTE:
        blockers.append(f"route_family must be {EXPECTED_ROUTE}")

    source_prs = _dict(data.get("source_prs"))
    for key, expected in REQUIRED_SOURCE_PRS.items():
        if source_prs.get(key) != expected:
            blockers.append(f"source_prs.{key} must be {expected}")

    authorizations = _dict(data.get("authorizations"))
    if authorizations.get("exact_route_cleanup_retry_authorized") is not True:
        blockers.append("authorizations.exact_route_cleanup_retry_authorized must be true")
    if authorizations.get("selected_route_family") != EXPECTED_ROUTE:
        blockers.append(f"authorizations.selected_route_family must be {EXPECTED_ROUTE}")
    for key in REQUIRED_FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    evidence = _dict(data.get("evidence_used"))
    if _dict(evidence.get("owner_approval")).get("owner") != "qianlan":
        blockers.append("owner approval must be qianlan")
    if _dict(evidence.get("rollback_owner")).get("owner") != "qianlan":
        blockers.append("rollback owner must be qianlan")
    if _dict(evidence.get("shadow_compare")).get("status") != "passed" or _dict(evidence.get("shadow_compare")).get("source_pr") != 813:
        blockers.append("shadow compare evidence must come from passed PR #813")
    if _dict(evidence.get("rollback_rehearsal")).get("status") != "passed" or _dict(evidence.get("rollback_rehearsal")).get("source_pr") != 813:
        blockers.append("rollback rehearsal evidence must come from passed PR #813")
    if _dict(evidence.get("route_ownership_proof")).get("status") != "collected" or _dict(evidence.get("route_ownership_proof")).get("source_pr") != 814:
        blockers.append("route ownership proof must come from PR #814")
    compat_evidence = _dict(evidence.get("production_compat_exact_entry_proof"))
    if compat_evidence.get("status") != "collected" or compat_evidence.get("source_pr") != 814:
        blockers.append("production_compat exact-entry proof must come from PR #814")
    if compat_evidence.get("wildcard_cleanup_required") is not False:
        blockers.append("wildcard cleanup must not be required")

    actions = _dict(data.get("cleanup_actions"))
    for key in ("fallback_removal_attempted", "fallback_removal_executed", "production_compat_cleanup_attempted", "production_compat_cleanup_executed"):
        if actions.get(key) is not True:
            blockers.append(f"cleanup_actions.{key} must be true")
    for key in ("wildcard_cleanup_executed", "runtime_deletion_executed", "delete_ready"):
        if actions.get(key) is not False:
            blockers.append(f"cleanup_actions.{key} must be false")

    rollback = _dict(data.get("rollback"))
    if rollback.get("rollback_available") is not True or rollback.get("rollback_owner") != "qianlan":
        blockers.append("rollback must be available and owned by qianlan")
    if not rollback.get("rollback_command") or not rollback.get("rollback_validation_command") or not rollback.get("rollback_evidence_path"):
        blockers.append("rollback command, validation command, and evidence path must be recorded")

    continuity = _dict(data.get("business_continuity"))
    if continuity.get("selected_exact_route_only") is not True:
        blockers.append("business_continuity.selected_exact_route_only must be true")
    for key in ("timer_execution_triggered", "outbound_send_triggered", "external_live_call_triggered", "high_risk_route_affected"):
        if continuity.get(key) is not False:
            blockers.append(f"business_continuity.{key} must be false")

    compat_text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    if _contains_decorator(compat_text, TASK_GROUPS_EXACT) or _contains_decorator(compat_text, f"{TASK_GROUPS_EXACT}/{{path:path}}"):
        blockers.append("task-groups production_compat decorators must be removed")
    for route in (
        "/api/admin/automation-conversion/workflow-nodes/{path:path}",
        "/api/admin/automation-conversion/tasks",
        "/api/admin/automation-conversion/tasks/{path:path}",
        "/api/admin/automation-conversion/workflows",
        "/api/admin/automation-conversion/workflows/{path:path}",
    ):
        if not _contains_decorator(compat_text, route):
            blockers.append(f"unrelated production_compat route must remain: {route}")
    if not _production_compat_diff_is_scoped():
        blockers.append("production_compat diff must only remove the two task-groups decorators")

    native_text = NATIVE_API.read_text(encoding="utf-8")
    if not re.search(rf'@router\.get\("{re.escape(TASK_GROUPS_EXACT)}"\)', native_text):
        blockers.append("native task-groups GET route must remain")
    if not re.search(rf'@router\.post\("{re.escape(TASK_GROUPS_EXACT)}"\)', native_text):
        blockers.append("native task-groups POST route must remain")

    entry = _route_manifest_entry()
    if entry.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("manifest task-groups capability_owner must be aicrm_next.automation_engine")
    if entry.get("current_runtime_owner") != "aicrm_next.automation_engine":
        blockers.append("manifest task-groups current_runtime_owner must be aicrm_next.automation_engine")
    if entry.get("production_behavior") != "next_native_exact_route":
        blockers.append("manifest task-groups production_behavior must be next_native_exact_route")
    if entry.get("legacy_fallback_allowed") is not False:
        blockers.append("manifest task-groups legacy_fallback_allowed must be false")
    if entry.get("delete_ready") is not False:
        blockers.append("manifest task-groups delete_ready must be false")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "task_groups_exact_route_cleanup_retry":
        blockers.append("phase_execution_state.active_candidate must be task_groups_exact_route_cleanup_retry")
    if state.get("last_merged_pr") != "#814":
        blockers.append("phase_execution_state.last_merged_pr must record #814")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_legacy_runtime_recheck_bundle"}:
        blockers.append("phase_execution_state.next_allowed_actions must select legacy runtime recheck")
    phase_state = _dict(state.get("post_phase7_cleanup_task_groups_exact_route_retry"))
    if phase_state.get("status") != "post_phase7_cleanup_task_groups_exact_route_retry_completed":
        blockers.append("state task-groups exact-route retry status must be completed")
    for key in ("fallback_removal_executed", "production_compat_cleanup_executed"):
        if phase_state.get(key) is not True:
            blockers.append(f"state {key} must be true")
    for key in ("wildcard_cleanup_executed", "runtime_deletion_executed", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"state {key} must be false")

    result = _dict(data.get("cleanup_result"))
    if result.get("status") != "cleanup_succeeded":
        blockers.append("cleanup_result.status must be cleanup_succeeded")
    if result.get("delete_ready") is not False:
        blockers.append("cleanup_result.delete_ready must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside task-groups exact-route retry allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Task-Groups Exact-Route Cleanup Retry Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
