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

DOC = ROOT / "docs/development/phase_6j_timer_execution_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_6j_timer_execution_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6j_timer_execution_readiness.py"
REQUIRED_CANDIDATES = {"task-groups", "tasks", "workflows", "workflow-nodes", "agent-runs", "agent-outputs", "group-ops plans / webhook"}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6j_timer_execution_readiness.md",
    "docs/development/phase_6j_timer_execution_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6j_timer_execution_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6j_timer_execution_readiness.py",
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
    if data.get("bundle_type") != "phase_6j_timer_execution_readiness_bundle":
        blockers.append("bundle_type must be phase_6j_timer_execution_readiness_bundle")
    if data.get("route_family") != "phase_6_timer_execution_readiness":
        blockers.append("route_family must be phase_6_timer_execution_readiness")
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    for key, value in _dict(data.get("readiness_policy")).items():
        if value is not True:
            blockers.append(f"readiness_policy.{key} must be true")

    candidates = _list(data.get("execution_candidate_inventory"))
    by_candidate = {str(item.get("candidate")): item for item in candidates if isinstance(item, dict)}
    if set(by_candidate) != REQUIRED_CANDIDATES:
        blockers.append(f"execution_candidate_inventory must include {sorted(REQUIRED_CANDIDATES)}")
    for name, item in by_candidate.items():
        for field in (
            "route_family",
            "capability",
            "execution_type",
            "required_external_adapter",
            "requires_outbound_send",
            "requires_timer",
            "requires_live_external_call",
            "can_be_dry_run",
            "can_be_single_scope_canary",
            "rollback_pause_strategy",
            "risk_level",
            "recommended_next_step",
        ):
            if field not in item:
                blockers.append(f"{name} missing {field}")
        if item.get("can_be_dry_run") is not True:
            blockers.append(f"{name}.can_be_dry_run must be true")
        if not item.get("rollback_pause_strategy"):
            blockers.append(f"{name}.rollback_pause_strategy must be non-empty")

    selected = _dict(data.get("first_execution_canary_candidate"))
    if selected.get("selected_candidate") != "workflow-nodes":
        blockers.append("first execution canary must select workflow-nodes")
    for key in ("requires_outbound_send", "requires_timer", "requires_live_external_call"):
        if selected.get(key) is not False:
            blockers.append(f"first_execution_canary_candidate.{key} must be false")
    for key in ("can_be_dry_run", "can_be_single_scope_canary"):
        if selected.get(key) is not True:
            blockers.append(f"first_execution_canary_candidate.{key} must be true")
    if selected.get("next_bundle") != "phase_6k_single_scope_execution_canary_tooling_bundle":
        blockers.append("first_execution_canary_candidate.next_bundle must be Phase 6K")

    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _list(data.get("next")) != ["phase_6k_single_scope_execution_canary_tooling_bundle"]:
        blockers.append("next must only recommend Phase 6K")

    if state.get("current_phase") != "phase_6j_timer_execution_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 6J")
    if state.get("active_candidate") != "timer_execution_readiness":
        blockers.append("phase_execution_state.active_candidate must be timer_execution_readiness")
    if state.get("last_merged_pr") != "#769":
        blockers.append("phase_execution_state.last_merged_pr must record PR #769")
    if state.get("recommended_next_pr") != "phase_6k_single_scope_execution_canary_tooling_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6K")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6J allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6J Timer Execution Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
