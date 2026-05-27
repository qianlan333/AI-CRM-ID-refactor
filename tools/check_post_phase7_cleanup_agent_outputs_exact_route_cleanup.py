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


DOC = ROOT / "docs/development/post_phase7_cleanup_agent_outputs_exact_route_cleanup.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_agent_outputs_exact_route_cleanup.yaml"
OWNER_YAML = ROOT / "docs/development/post_phase7_cleanup_owner_standing_approval.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
NATIVE_API = ROOT / "aicrm_next/automation_engine/api.py"

EXPECTED_ROUTE_FAMILY = "/api/admin/automation-conversion/agent-outputs*"
SELECTED_EXACT_ROUTE = "/api/admin/automation-conversion/agent-outputs"
SELECTED_DECORATOR = '@router.api_route("/api/admin/automation-conversion/agent-outputs", methods=_ALL_METHODS)'
RETAINED_WILDCARD = '@router.api_route("/api/admin/automation-conversion/agent-outputs/{path:path}", methods=_ALL_METHODS)'
NEXT_NATIVE_PATTERN = r'@router\.get\("/api/admin/automation-conversion/agent-outputs"\)'

RETAINED_ROUTES = (
    '"/api/admin/automation-conversion/agent-outputs/{path:path}"',
    '"/api/admin/automation-conversion/agent-runs/{path:path}"',
    '"/api/admin/automation-conversion/agents"',
    '"/api/admin/automation-conversion/agents/{path:path}"',
    '"/api/admin/automation-conversion/action-templates"',
    '"/api/admin/automation-conversion/action-templates/{path:path}"',
    '"/api/admin/automation-conversion/tasks"',
    '"/api/admin/automation-conversion/tasks/{path:path}"',
    '"/api/admin/automation-conversion/workflows"',
    '"/api/admin/automation-conversion/workflows/{path:path}"',
    "wildcard_router",
)

ALLOWED_CHANGED_FILES = {
    "aicrm_next/production_compat/api.py",
    "docs/development/post_phase7_cleanup_owner_standing_approval.md",
    "docs/development/post_phase7_cleanup_owner_standing_approval.yaml",
    "docs/development/post_phase7_cleanup_agent_outputs_exact_route_cleanup.md",
    "docs/development/post_phase7_cleanup_agent_outputs_exact_route_cleanup.yaml",
    "docs/development/phase_execution_state.yaml",
    "docs/route_ownership/production_route_ownership_manifest.yaml",
    "docs/development/legacy_replacement_backlog.md",
    "docs/development/legacy_replacement_backlog.yaml",
    "tools/check_post_phase7_cleanup_agent_outputs_exact_route_cleanup.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_cleanup_agent_outputs_exact_route_cleanup.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "aicrm_next/main.py"}
FORBIDDEN_PREFIXES = ("wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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


def _manifest_entry(route_pattern: str) -> dict[str, Any]:
    data = load_yaml(MANIFEST)
    for item in _list(data.get("routes")):
        if isinstance(item, dict) and item.get("route_pattern") == route_pattern:
            return item
    return {}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, PLAN_YAML, OWNER_YAML, STATE, MANIFEST, BACKLOG, PRODUCTION_COMPAT, NATIVE_API):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    owner = load_yaml(OWNER_YAML)
    state = load_yaml(STATE)
    manifest_entry = _manifest_entry(EXPECTED_ROUTE_FAMILY)
    compat_text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    native_text = NATIVE_API.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("status") != "post_phase7_cleanup_agent_outputs_exact_route_cleanup":
        blockers.append("cleanup status is incorrect")
    if data.get("bundle_type") != "post_phase7_cleanup_agent_outputs_exact_route_cleanup_bundle":
        blockers.append("bundle_type is incorrect")
    if data.get("route_family") != EXPECTED_ROUTE_FAMILY:
        blockers.append(f"route_family must be {EXPECTED_ROUTE_FAMILY}")
    if data.get("selected_exact_route") != SELECTED_EXACT_ROUTE:
        blockers.append(f"selected_exact_route must be {SELECTED_EXACT_ROUTE}")

    approval = _dict(owner.get("owner_approval"))
    if approval.get("status") != "granted" or approval.get("owner") != "qianlan":
        blockers.append("standing owner approval must be granted by qianlan")
    if owner.get("runtime_deletion_policy", {}).get("runtime_deletion_authorized") is not False:
        blockers.append("standing approval must not authorize runtime deletion")
    if owner.get("delete_ready") is not False:
        blockers.append("standing approval must keep delete_ready false")

    auth = _dict(data.get("authorizations"))
    if auth.get("selected_exact_route_cleanup_authorized") is not True:
        blockers.append("selected exact-route cleanup must be authorized")
    if auth.get("owner") != "qianlan" or auth.get("rollback_owner") != "qianlan":
        blockers.append("owner and rollback_owner must be qianlan")
    for key in (
        "broad_fallback_removal_authorized",
        "wildcard_production_compat_cleanup_authorized",
        "runtime_deletion_authorized",
        "payment_oauth_wecom_callback_timer_outbound_affected",
        "delete_ready",
    ):
        if auth.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    if SELECTED_DECORATOR in compat_text:
        blockers.append("selected agent-outputs exact production_compat decorator must be removed")
    if RETAINED_WILDCARD not in compat_text:
        blockers.append("agent-outputs wildcard production_compat decorator must remain")
    for route in RETAINED_ROUTES:
        if route not in compat_text:
            blockers.append(f"retained route missing from production_compat: {route}")
    if not re.search(NEXT_NATIVE_PATTERN, native_text):
        blockers.append("Next-native GET /agent-outputs route must exist")

    evidence = _dict(data.get("replacement_evidence"))
    next_native = _dict(evidence.get("next_native_exact_route"))
    if next_native.get("status") != "present" or next_native.get("route") != SELECTED_EXACT_ROUTE:
        blockers.append("replacement evidence must record the Next-native exact route")
    if evidence.get("production_repository_unavailable_payload_retained") is not True:
        blockers.append("production unavailable payload evidence must be retained")
    if evidence.get("external_side_effects_executed") is not False:
        blockers.append("external side effects must not execute")

    cleanup = _dict(data.get("cleanup_actions"))
    if cleanup.get("production_compat_exact_entry_removed") is not True:
        blockers.append("cleanup_actions.production_compat_exact_entry_removed must be true")
    if cleanup.get("subpath_fallback_retained") is not True:
        blockers.append("cleanup_actions.subpath_fallback_retained must be true")
    for key in ("wildcard_router_retained",):
        if cleanup.get(key) is not True:
            blockers.append(f"cleanup_actions.{key} must be true")
    for key in ("runtime_deletion_executed", "delete_ready"):
        if cleanup.get(key) is not False:
            blockers.append(f"cleanup_actions.{key} must be false")

    result = _dict(data.get("cleanup_result"))
    if SELECTED_EXACT_ROUTE not in _list(result.get("production_compat_cleanups_executed")):
        blockers.append("cleanup_result must record selected exact route cleanup")
    if result.get("agent_outputs_wildcard_fallback_retained") is not True:
        blockers.append("cleanup_result must record retained agent-outputs wildcard fallback")
    if result.get("wildcard_cleanup_executed") is not False:
        blockers.append("wildcard cleanup must be false")
    if _list(result.get("runtime_deletions_executed")):
        blockers.append("runtime deletions must be empty")
    if result.get("delete_ready") is not False:
        blockers.append("cleanup_result.delete_ready must be false")

    if manifest_entry.get("current_runtime_owner") != "production_compat":
        blockers.append("agent-outputs route family owner must remain production_compat while wildcard is retained")
    if manifest_entry.get("legacy_fallback_allowed") is not True:
        blockers.append("agent-outputs legacy fallback must remain allowed for retained subpaths")
    if "exact /api/admin/automation-conversion/agent-outputs production_compat decorator" not in str(manifest_entry.get("notes", "")):
        blockers.append("manifest notes must record exact-entry cleanup")
    if "exact /api/admin/automation-conversion/agent-outputs production_compat decorator" not in backlog_text:
        blockers.append("legacy replacement backlog must record exact-entry cleanup evidence")

    if state.get("current_phase") != "post_phase7_cleanup_agent_outputs_exact_route_cleanup":
        blockers.append("phase state current_phase must be agent-outputs exact-route cleanup")
    if state.get("active_candidate") != EXPECTED_ROUTE_FAMILY:
        blockers.append("phase state active_candidate must be agent-outputs route family")
    phase = _dict(state.get("post_phase7_cleanup_agent_outputs_exact_route_cleanup"))
    if phase.get("exact_production_compat_entry_removed") is not True:
        blockers.append("phase state must record exact production_compat entry removal")
    if phase.get("wildcard_production_compat_entry_retained") is not True:
        blockers.append("phase state must retain wildcard production_compat entry")
    if phase.get("runtime_deletion_executed") is not False or phase.get("delete_ready") is not False:
        blockers.append("phase state must keep runtime deletion and delete_ready false")

    forbidden_claims = {
        "runtime deletion executed: true",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
        "wildcard cleanup executed: true",
    }
    if any(claim in doc_text for claim in forbidden_claims):
        blockers.append("docs must not claim runtime deletion, wildcard cleanup, or delete_ready true")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside agent-outputs cleanup allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"forbidden protected/runtime files changed: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Agent-Outputs Exact-Route Cleanup Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
