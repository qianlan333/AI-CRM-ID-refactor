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


DOC = ROOT / "docs/development/post_phase7_cleanup_legacy_runtime_recheck.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_legacy_runtime_recheck.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
TEST = ROOT / "tests/test_post_phase7_cleanup_legacy_runtime_recheck.py"
EXPECTED_STATUS = "post_phase7_cleanup_legacy_runtime_recheck"
EXPECTED_BUNDLE = "post_phase7_cleanup_legacy_runtime_recheck_bundle"
TASK_GROUPS_EXACT = "/api/admin/automation-conversion/task-groups"
WORKFLOW_NODES_EXACT = "/api/admin/automation-conversion/workflow-nodes"
AGENT_OUTPUTS_EXACT = "/api/admin/automation-conversion/agent-outputs"
AGENT_OUTPUTS_WILDCARD = "/api/admin/automation-conversion/agent-outputs/{path:path}"
RETAINED_PRODUCTION_COMPAT_ROUTES = (
    AGENT_OUTPUTS_WILDCARD,
    "/api/admin/automation-conversion/agent-runs/{path:path}",
    "/api/admin/automation-conversion/tasks",
    "/api/admin/automation-conversion/tasks/{path:path}",
    "/api/admin/automation-conversion/workflows",
    "/api/admin/automation-conversion/workflows/{path:path}",
    "/api/admin/automation-conversion/agents",
    "/api/admin/automation-conversion/agents/{path:path}",
    "/api/admin/wechat-pay/{path:path}",
    "/api/h5/wechat/oauth/{path:path}",
    "/api/h5/questionnaires/{slug}/submit",
)
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_cleanup_legacy_runtime_recheck.md",
    "docs/development/post_phase7_cleanup_legacy_runtime_recheck.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_cleanup_legacy_runtime_recheck.py",
    "tools/check_post_phase7_cleanup_agent_outputs_exact_route_cleanup.py",
    "tools/check_post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_legacy_runtime_recheck.py",
    "tests/test_post_phase7_cleanup_agent_outputs_exact_route_cleanup.py",
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


def _contains_decorator(text: str, route: str) -> bool:
    return f'"{route}"' in text or f"'{route}'" in text


def _route_manifest(route_pattern: str) -> dict[str, Any]:
    data = load_yaml(MANIFEST)
    for entry in _list(data.get("routes")):
        if isinstance(entry, dict) and entry.get("route_pattern") == route_pattern:
            return entry
    return {}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, MANIFEST, PRODUCTION_COMPAT, TEST):
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
    if data.get("cleanup_family") != "legacy_runtime_recheck_after_exact_route_cleanup":
        blockers.append("cleanup_family must be legacy_runtime_recheck_after_exact_route_cleanup")

    source_prs = _dict(data.get("source_prs"))
    if source_prs.get("task_groups_exact_route_retry") != 815:
        blockers.append("source_prs.task_groups_exact_route_retry must be 815")
    if source_prs.get("task_groups_legacy_runtime_recheck") != 816:
        blockers.append("source_prs.task_groups_legacy_runtime_recheck must be 816")
    if source_prs.get("cleanup_track_acceptance") != 817:
        blockers.append("source_prs.cleanup_track_acceptance must be 817")
    if source_prs.get("workflow_nodes_owner_approved_cleanup") != 818:
        blockers.append("source_prs.workflow_nodes_owner_approved_cleanup must be 818")
    if source_prs.get("post_818_legacy_runtime_recheck") != 819:
        blockers.append("source_prs.post_818_legacy_runtime_recheck must be 819")
    if source_prs.get("agent_outputs_exact_route_cleanup") != 820:
        blockers.append("source_prs.agent_outputs_exact_route_cleanup must be 820")

    authorizations = _dict(data.get("authorizations"))
    for key in (
        "runtime_deletion_authorized",
        "fallback_removal_authorized",
        "production_compat_cleanup_authorized",
        "wildcard_cleanup_authorized",
        "delete_ready",
        "production_behavior_change_authorized",
    ):
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    handoff = _dict(data.get("exact_route_cleanup_handoff"))
    if handoff.get("task_groups_fallback_removal_executed") is not True:
        blockers.append("task-groups fallback cleanup handoff must be true")
    if handoff.get("task_groups_production_compat_cleanup_executed") is not True:
        blockers.append("task-groups production_compat cleanup handoff must be true")
    if handoff.get("workflow_nodes_production_compat_cleanup_executed") is not True:
        blockers.append("workflow-nodes production_compat cleanup handoff must be true")
    if handoff.get("workflow_nodes_production_compat_hook_absent") is not True:
        blockers.append("workflow-nodes production_compat hook must be absent in handoff")
    if handoff.get("agent_outputs_exact_production_compat_cleanup_executed") is not True:
        blockers.append("agent-outputs exact production_compat cleanup handoff must be true")
    if handoff.get("agent_outputs_exact_production_compat_hook_absent") is not True:
        blockers.append("agent-outputs exact production_compat hook must be absent in handoff")
    if handoff.get("agent_outputs_wildcard_production_compat_retained") is not True:
        blockers.append("agent-outputs wildcard production_compat must be retained in handoff")
    for key in ("wildcard_cleanup_executed", "runtime_deletion_executed", "delete_ready"):
        if handoff.get(key) is not False:
            blockers.append(f"exact_route_cleanup_handoff.{key} must be false")

    recheck = _dict(data.get("reference_recheck"))
    for key in (
        "task_groups_production_compat_hooks_absent",
        "workflow_nodes_production_compat_hook_absent",
        "workflow_nodes_manifest_owner_next",
        "agent_outputs_exact_production_compat_hook_absent",
        "agent_outputs_wildcard_production_compat_retained",
        "agent_outputs_manifest_owner_production_compat",
        "agent_outputs_legacy_fallback_allowed",
        "agent_outputs_legacy_runtime_references_retained",
        "other_production_compat_routes_retained",
        "wildcard_router_retained",
        "fallback_references_retained",
        "tests_reference_legacy_or_retained_routes",
        "route_ownership_manifest_retains_legacy_runtime_categories",
        "wecom_ability_service_references_retained",
    ):
        if recheck.get(key) is not True:
            blockers.append(f"reference_recheck.{key} must be true")
    if recheck.get("workflow_nodes_legacy_fallback_allowed") is not False:
        blockers.append("reference_recheck.workflow_nodes_legacy_fallback_allowed must be false")
    if not _list(recheck.get("high_risk_runtime_categories_retained")):
        blockers.append("high_risk_runtime_categories_retained must not be empty")

    result = _dict(data.get("runtime_candidate_result"))
    if result.get("safe_runtime_cleanup_candidate_selected") is not False:
        blockers.append("safe_runtime_cleanup_candidate_selected must be false")
    if result.get("no_safe_runtime_cleanup_candidate") is not True:
        blockers.append("no_safe_runtime_cleanup_candidate must be true")
    if _list(result.get("safe_deletion_candidates")):
        blockers.append("safe_deletion_candidates must be empty")
    blocked_candidates = _list(result.get("blocked_candidates"))
    if not blocked_candidates:
        blockers.append("blocked_candidates must not be empty")
    elif not any(isinstance(item, dict) and item.get("route_family") == "/api/admin/automation-conversion/agent-outputs*" for item in blocked_candidates):
        blockers.append("blocked_candidates must include agent-outputs")
    if not _list(result.get("retained_old_code_categories")):
        blockers.append("retained_old_code_categories must not be empty")
    if not _list(result.get("blocked_reason")):
        blockers.append("blocked_reason must list why runtime deletion is unsafe")

    cleanup = _dict(data.get("cleanup_execution"))
    for key in (
        "runtime_deletion_executed",
        "fallback_removal_executed_in_this_pr",
        "production_compat_cleanup_executed_in_this_pr",
        "wildcard_cleanup_executed",
        "delete_ready",
    ):
        if cleanup.get(key) is not False:
            blockers.append(f"cleanup_execution.{key} must be false")

    continuity = _dict(data.get("business_continuity"))
    if continuity.get("production_behavior_unchanged") is not True:
        blockers.append("business_continuity.production_behavior_unchanged must be true")
    if continuity.get("legacy_runtime_retained") is not True:
        blockers.append("business_continuity.legacy_runtime_retained must be true")
    for key in (
        "task_groups_cleanup_retained",
        "workflow_nodes_cleanup_retained",
        "agent_outputs_exact_cleanup_retained",
        "agent_outputs_wildcard_fallback_retained",
        "unrelated_production_compat_retained",
        "wildcard_router_retained",
    ):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if continuity.get("runtime_deletion_executed") is not False:
        blockers.append("business_continuity.runtime_deletion_executed must be false")
    if continuity.get("delete_ready") is not False:
        blockers.append("business_continuity.delete_ready must be false")

    compat_text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    if _contains_decorator(compat_text, TASK_GROUPS_EXACT) or _contains_decorator(compat_text, f"{TASK_GROUPS_EXACT}/{{path:path}}"):
        blockers.append("task-groups production_compat hooks must remain absent after #815")
    if _contains_decorator(compat_text, f"{WORKFLOW_NODES_EXACT}/{{path:path}}"):
        blockers.append("workflow-nodes production_compat hook must be absent after #818")
    if _contains_decorator(compat_text, AGENT_OUTPUTS_EXACT):
        blockers.append("agent-outputs exact production_compat hook must be absent after #820")
    if not _contains_decorator(compat_text, AGENT_OUTPUTS_WILDCARD):
        blockers.append("agent-outputs wildcard production_compat hook must remain after #820")
    if "wildcard_router" not in compat_text:
        blockers.append("wildcard_router must remain retained")
    for route in RETAINED_PRODUCTION_COMPAT_ROUTES:
        if not _contains_decorator(compat_text, route):
            blockers.append(f"retained production_compat route missing: {route}")

    task_groups = _route_manifest("/api/admin/automation-conversion/task-groups*")
    workflow_nodes = _route_manifest("/api/admin/automation-conversion/workflow-nodes*")
    agent_outputs = _route_manifest("/api/admin/automation-conversion/agent-outputs*")
    if task_groups.get("current_runtime_owner") != "aicrm_next.automation_engine":
        blockers.append("task-groups manifest owner must remain Next-native after #815")
    if task_groups.get("legacy_fallback_allowed") is not False:
        blockers.append("task-groups legacy_fallback_allowed must remain false")
    if workflow_nodes.get("current_runtime_owner") != "next":
        blockers.append("workflow-nodes manifest owner must be next after #818")
    if workflow_nodes.get("legacy_fallback_allowed") is not False:
        blockers.append("workflow-nodes legacy_fallback_allowed must be false after #818")
    if agent_outputs.get("current_runtime_owner") != "production_compat":
        blockers.append("agent-outputs manifest owner must remain production_compat while wildcard is retained")
    if agent_outputs.get("legacy_fallback_allowed") is not True:
        blockers.append("agent-outputs legacy_fallback_allowed must remain true while wildcard is retained")

    if state.get("current_phase") != EXPECTED_STATUS:
        blockers.append(f"phase_execution_state.current_phase must be {EXPECTED_STATUS}")
    if state.get("active_candidate") != "legacy_runtime_recheck_after_agent_outputs_exact_cleanup":
        blockers.append("active_candidate must be legacy_runtime_recheck_after_agent_outputs_exact_cleanup")
    if state.get("last_merged_pr") != "#820":
        blockers.append("last_merged_pr must record #820")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_track_acceptance_bundle"}:
        blockers.append("next_allowed_actions must select cleanup track acceptance")
    phase_state = _dict(state.get("post_phase7_cleanup_legacy_runtime_recheck"))
    if phase_state.get("status") != "post_phase7_cleanup_legacy_runtime_recheck_completed":
        blockers.append("state legacy runtime recheck status must be completed")
    if phase_state.get("safe_runtime_cleanup_candidate_selected") is not False:
        blockers.append("state safe_runtime_cleanup_candidate_selected must be false")
    if phase_state.get("no_safe_runtime_cleanup_candidate") is not True:
        blockers.append("state no_safe_runtime_cleanup_candidate must be true")
    if phase_state.get("runtime_deletion_executed") is not False:
        blockers.append("state runtime_deletion_executed must be false")
    if phase_state.get("delete_ready") is not False:
        blockers.append("state delete_ready must be false")
    if phase_state.get("workflow_nodes_production_compat_hook_absent") is not True:
        blockers.append("state workflow_nodes_production_compat_hook_absent must be true")
    if phase_state.get("agent_outputs_exact_production_compat_hook_absent") is not True:
        blockers.append("state agent_outputs_exact_production_compat_hook_absent must be true")
    if phase_state.get("agent_outputs_wildcard_production_compat_retained") is not True:
        blockers.append("state agent_outputs_wildcard_production_compat_retained must be true")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside legacy runtime recheck allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Legacy Runtime Recheck", "", f"- overall: {report['overall']}", "- blockers:"]
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
