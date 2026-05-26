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

DOC = ROOT / "docs/development/phase_7k_final_route_ownership_manifest_cleanup.md"
PLAN_YAML = ROOT / "docs/development/phase_7k_final_route_ownership_manifest_cleanup.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7k_final_route_ownership_manifest_cleanup.py"
NEXT_BUNDLE = "phase_7l_final_legacy_retirement_acceptance_bundle"
FALSE_AUTHORIZATIONS = {
    "route_owner_behavior_change_authorized",
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "legacy_runtime_deletion_authorized",
    "delete_ready",
}
REQUIRED_FAMILIES = {
    "profile-segment-templates*",
    "action-templates*",
    "task-groups*",
    "workflow-nodes*",
    "tasks*",
    "workflows*",
    "agents*",
    "agent-runs*",
    "agent-outputs*",
    "WeCom tags",
    "WeCom contact callback",
    "OAuth identity",
    "Media upload / media library",
    "Payment / commerce",
    "OpenClaw / MCP / AI assist",
    "Questionnaire external submit / tag writeback",
}
REQUIRED_FIELDS = {
    "current_owner",
    "next_owner_ready",
    "fallback_retained",
    "production_compat_retained",
    "owner_switch_tooling_status",
    "fallback_cleanup_status",
    "production_compat_cleanup_status",
    "runtime_cleanup_status",
    "delete_ready",
    "blockers",
    "next_possible_action",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7k_final_route_ownership_manifest_cleanup.md",
    "docs/development/phase_7k_final_route_ownership_manifest_cleanup.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7k_final_route_ownership_manifest_cleanup.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7k_final_route_ownership_manifest_cleanup.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "docs/route_ownership/production_route_ownership_manifest.yaml"}


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
    if data.get("bundle_type") != "phase_7k_final_route_ownership_manifest_cleanup_bundle":
        blockers.append("bundle_type must be phase_7k_final_route_ownership_manifest_cleanup_bundle")
    for key in FALSE_AUTHORIZATIONS:
        if _dict(data.get("authorizations")).get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")
    families = _list(data.get("route_families"))
    family_names = {str(item.get("family")) for item in families if isinstance(item, dict)}
    missing = sorted(REQUIRED_FAMILIES - family_names)
    if missing:
        blockers.append(f"route_families missing required families: {missing}")
    for item in families:
        if not isinstance(item, dict):
            blockers.append("route_families entries must be objects")
            continue
        missing_fields = sorted(REQUIRED_FIELDS - set(item))
        if missing_fields:
            blockers.append(f"route family {item.get('family')} missing fields: {missing_fields}")
        if item.get("fallback_retained") is not True:
            blockers.append(f"route family {item.get('family')} must retain fallback")
        if item.get("production_compat_retained") is not True:
            blockers.append(f"route family {item.get('family')} must retain production_compat")
        if item.get("delete_ready") is not False:
            blockers.append(f"route family {item.get('family')} delete_ready must be false")
        if not _list(item.get("blockers")):
            blockers.append(f"route family {item.get('family')} blockers must not be empty")
    outcome = _dict(data.get("outcome"))
    if outcome.get("consolidation_only") is not True:
        blockers.append("outcome.consolidation_only must be true")
    for key in ("production_behavior_changed", "route_owner_behavior_changed", "fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if outcome.get(key) is not False:
            blockers.append(f"outcome.{key} must be false")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7L")
    if state.get("current_phase") != "phase_7k_final_route_ownership_manifest_cleanup":
        blockers.append("phase_execution_state.current_phase must be Phase 7K")
    if state.get("active_candidate") != "final_route_ownership_manifest_cleanup":
        blockers.append("phase_execution_state.active_candidate must be final route ownership cleanup")
    if state.get("last_merged_pr") != "#791":
        blockers.append("phase_execution_state.last_merged_pr must record PR #791")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7L")
    phase_state = _dict(state.get("phase7k_final_route_ownership_manifest_cleanup"))
    for key in ("route_owner_behavior_changed", "fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"phase7k state {key} must be false")
    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7K allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7K Final Route Ownership Cleanup Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
