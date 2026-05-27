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


DOC = ROOT / "docs/development/post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.yaml"
OWNER_YAML = ROOT / "docs/development/post_phase7_cleanup_workflow_nodes_owner_approval.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
NATIVE_API = ROOT / "aicrm_next/automation_engine/api.py"

EXPECTED_ROUTE = "/api/admin/automation-conversion/workflow-nodes*"
REMOVED_COMPAT_DECORATOR = '@router.api_route("/api/admin/automation-conversion/workflow-nodes/{path:path}", methods=_ALL_METHODS)'

REQUIRED_FALSE_AUTHORIZATIONS = {
    "broad_fallback_removal_authorized",
    "wildcard_production_compat_cleanup_authorized",
    "runtime_deletion_authorized",
    "payment_oauth_wecom_callback_timer_outbound_affected",
    "delete_ready",
}

RETAINED_ROUTES = [
    '"/api/admin/automation-conversion/tasks"',
    '"/api/admin/automation-conversion/tasks/{path:path}"',
    '"/api/admin/automation-conversion/workflows"',
    '"/api/admin/automation-conversion/workflows/{path:path}"',
    '"/api/admin/automation-conversion/agents"',
    '"/api/admin/automation-conversion/agents/{path:path}"',
    '"/api/admin/wechat-pay/{path:path}"',
    '"/api/h5/wechat/oauth/{path:path}"',
    '"/api/h5/questionnaires/{slug}/submit"',
    "wildcard_router",
]

NATIVE_REQUIRED_PATTERNS = {
    "workflow_nodes_exact_get": r'@router\.get\("/api/admin/automation-conversion/workflow-nodes"\)',
    "workflow_nodes_exact_post": r'@router\.post\("/api/admin/automation-conversion/workflow-nodes"\)',
    "workflow_scoped_nodes_get": r'@router\.get\("/api/admin/automation-conversion/workflows/\{workflow_id\}/nodes"\)',
    "workflow_scoped_nodes_post": r'@router\.post\("/api/admin/automation-conversion/workflows/\{workflow_id\}/nodes"\)',
    "workflow_node_put": r'@router\.put\("/api/admin/automation-conversion/workflow-nodes/\{node_id\}"\)',
    "workflow_node_delete": r'@router\.delete\("/api/admin/automation-conversion/workflow-nodes/\{node_id\}"\)',
}

ALLOWED_CHANGED_FILES = {
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/workflow_nodes.py",
    "aicrm_next/production_compat/api.py",
    "docs/development/post_phase7_cleanup_workflow_nodes_owner_approval.md",
    "docs/development/post_phase7_cleanup_workflow_nodes_owner_approval.yaml",
    "docs/development/post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.md",
    "docs/development/post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.yaml",
    "docs/development/phase_execution_state.yaml",
    "docs/route_ownership/production_route_ownership_manifest.yaml",
    "docs/development/legacy_replacement_backlog.yaml",
    "docs/development/legacy_replacement_backlog.md",
    "tools/check_post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_CHANGED_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_CHANGED_PREFIXES = ("migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_DELETED_PREFIXES = ("wecom_ability_service/",)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return proc.stdout if proc.returncode == 0 else ""


def _changed_files() -> set[str]:
    files: set[str] = set()
    for args in (
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        files.update(line.strip() for line in _run_git(args).splitlines() if line.strip())
    return files


def _deleted_or_renamed_files() -> list[str]:
    return [
        line
        for line in _run_git(["diff", "--name-status", "origin/main...HEAD"]).splitlines()
        if line.startswith(("D", "R"))
    ]


def _manifest_entry(route_pattern: str) -> dict[str, Any]:
    data = load_yaml(MANIFEST)
    for item in _list(data.get("routes")):
        if isinstance(item, dict) and item.get("route_pattern") == route_pattern:
            return item
    return {}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, PLAN_YAML, OWNER_YAML, STATE, MANIFEST, PRODUCTION_COMPAT, NATIVE_API):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    owner = load_yaml(OWNER_YAML)
    state = load_yaml(STATE)
    manifest_entry = _manifest_entry(EXPECTED_ROUTE)

    if data.get("status") != "post_phase7_cleanup_workflow_nodes_owner_approved_cleanup":
        blockers.append("cleanup status is incorrect")
    if data.get("bundle_type") != "post_phase7_cleanup_workflow_nodes_owner_approved_cleanup_bundle":
        blockers.append("bundle_type is incorrect")
    if data.get("cleanup_family") != "workflow_nodes_owner_approved_exact_route_cleanup":
        blockers.append("cleanup_family is incorrect")
    if data.get("route_family") != EXPECTED_ROUTE:
        blockers.append(f"route_family must be {EXPECTED_ROUTE}")

    auth = _dict(data.get("authorizations"))
    if auth.get("owner_approval_status") != "granted":
        blockers.append("owner approval must be granted")
    if auth.get("owner") != "qianlan":
        blockers.append("owner must be qianlan")
    if auth.get("rollback_owner") != "qianlan":
        blockers.append("rollback_owner must be qianlan")
    if auth.get("selected_route_family") != EXPECTED_ROUTE:
        blockers.append(f"selected_route_family must be {EXPECTED_ROUTE}")
    for key in REQUIRED_FALSE_AUTHORIZATIONS:
        if auth.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    owner_approval = _dict(owner.get("owner_approval"))
    if owner_approval.get("status") != "granted" or owner_approval.get("owner") != "qianlan":
        blockers.append("owner approval artifact must record qianlan granted approval")
    if owner.get("runtime_deletion_authorized") is not False or owner.get("delete_ready") is not False:
        blockers.append("owner approval artifact must not authorize runtime deletion or delete_ready")

    compat_text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    if REMOVED_COMPAT_DECORATOR in compat_text:
        blockers.append("selected workflow-nodes production_compat decorator must be removed")
    for route in RETAINED_ROUTES:
        if route not in compat_text:
            blockers.append(f"unrelated retained route missing: {route}")

    native_text = NATIVE_API.read_text(encoding="utf-8")
    for label, pattern in NATIVE_REQUIRED_PATTERNS.items():
        if not re.search(pattern, native_text):
            blockers.append(f"missing Next-native replacement route: {label}")

    replacement = _dict(data.get("replacement_verification"))
    if replacement.get("workflow_nodes_next_native_replacement_verified") is not True:
        blockers.append("replacement_verification.workflow_nodes_next_native_replacement_verified must be true")
    if replacement.get("delete_semantics") != "safe_archive_tombstone":
        blockers.append("delete semantics must be safe archive/tombstone")
    if replacement.get("production_repository_unavailable_payload_retained") is not True:
        blockers.append("production unavailable payload must be retained")
    if replacement.get("external_side_effects_executed") is not False:
        blockers.append("external side effects must not execute")

    cleanup_actions = _dict(data.get("cleanup_actions"))
    if cleanup_actions.get("production_compat_cleanup_executed") is not True:
        blockers.append("production_compat_cleanup_executed must be true")
    if cleanup_actions.get("fallback_removal_scope") != "selected_workflow_nodes_entry_only":
        blockers.append("fallback removal scope must stay selected-route only")
    for key in ("wildcard_cleanup_executed", "runtime_deletion_executed", "delete_ready"):
        if cleanup_actions.get(key) is not False:
            blockers.append(f"cleanup_actions.{key} must be false")

    continuity = _dict(data.get("business_continuity"))
    if continuity.get("legacy_runtime_retained") is not True:
        blockers.append("legacy runtime must be retained")
    if continuity.get("unrelated_production_compat_routes_retained") is not True:
        blockers.append("unrelated production_compat routes must be retained")
    for key in ("timer_execution_triggered", "outbound_send_triggered", "external_live_call_triggered", "high_risk_route_affected"):
        if continuity.get(key) is not False:
            blockers.append(f"business_continuity.{key} must be false")

    cleanup_result = _dict(data.get("cleanup_result"))
    if cleanup_result.get("status") != "cleanup_succeeded":
        blockers.append("cleanup_result.status must be cleanup_succeeded")
    if EXPECTED_ROUTE not in _list(cleanup_result.get("production_compat_cleanups_executed")):
        blockers.append("cleanup_result must record workflow-nodes production_compat cleanup")
    if cleanup_result.get("delete_ready") is not False:
        blockers.append("cleanup_result.delete_ready must be false")
    if _list(cleanup_result.get("runtime_deletions_executed")):
        blockers.append("runtime_deletions_executed must be empty")

    if state.get("current_phase") != "post_phase7_cleanup_workflow_nodes_owner_approved_cleanup":
        blockers.append("phase state must advance to workflow-nodes owner-approved cleanup")
    if state.get("active_candidate") != "workflow_nodes_owner_approved_exact_route_cleanup":
        blockers.append("phase state active_candidate is incorrect")
    if state.get("recommended_next_pr") != "post_phase7_cleanup_legacy_runtime_recheck_bundle":
        blockers.append("next recommended PR must be legacy runtime recheck")
    if set(_list(state.get("next_allowed_actions"))) != {"post_phase7_cleanup_legacy_runtime_recheck_bundle"}:
        blockers.append("next_allowed_actions must only allow legacy runtime recheck")
    phase = _dict(state.get("post_phase7_cleanup_workflow_nodes_owner_approved_cleanup"))
    if phase.get("production_compat_cleanup_executed") is not True:
        blockers.append("phase state must record workflow-nodes production_compat cleanup")
    if phase.get("runtime_deletion_executed") is not False or phase.get("delete_ready") is not False:
        blockers.append("phase state must keep runtime_deletion_executed/delete_ready false")

    if manifest_entry.get("current_runtime_owner") != "next":
        blockers.append("workflow-nodes manifest owner must be next")
    if manifest_entry.get("legacy_fallback_allowed") is not False:
        blockers.append("workflow-nodes manifest legacy_fallback_allowed must be false")
    if manifest_entry.get("delete_ready") is not False:
        blockers.append("workflow-nodes manifest delete_ready must remain false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside workflow-nodes cleanup allowlist: {unexpected}")
    forbidden = sorted(
        path
        for path in changed
        if path in FORBIDDEN_CHANGED_EXACT or path.startswith(FORBIDDEN_CHANGED_PREFIXES)
    )
    if forbidden:
        blockers.append(f"forbidden protected/deploy files changed: {forbidden}")
    forbidden_deleted = [
        line
        for line in _deleted_or_renamed_files()
        if (line.split("\t")[-1] if "\t" in line else line).startswith(FORBIDDEN_DELETED_PREFIXES)
    ]
    if forbidden_deleted:
        blockers.append("legacy runtime files must not be deleted or renamed: " + ", ".join(forbidden_deleted))

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Workflow-Nodes Owner-Approved Cleanup Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
