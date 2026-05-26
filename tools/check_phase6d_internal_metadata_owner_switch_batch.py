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

DOC = ROOT / "docs/development/phase_6d_internal_metadata_owner_switch_batch.md"
PLAN_YAML = ROOT / "docs/development/phase_6d_internal_metadata_owner_switch_batch.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6d_internal_metadata_owner_switch_batch.py"
RUNNER = ROOT / "tools/run_phase6d_internal_metadata_owner_switch_batch.py"
SELECTED = {
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/workflow-nodes*",
    "/api/admin/automation-conversion/agent-outputs*",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6d_internal_metadata_owner_switch_batch.md",
    "docs/development/phase_6d_internal_metadata_owner_switch_batch.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6d_internal_metadata_owner_switch_batch.py",
    "tools/run_phase6d_internal_metadata_owner_switch_batch.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6d_internal_metadata_owner_switch_batch.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}


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


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


def _run_runner() -> dict[str, Any]:
    proc = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return {"overall": "FAIL", "stderr": proc.stderr}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"overall": "FAIL", "stdout": proc.stdout}


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
    if _strings(data.get("selected_route_families")) != SELECTED:
        blockers.append("selected_route_families must exactly match the Phase 6D low-risk batch")
    excluded_text = " ".join(_strings(data.get("excluded_route_families"))).lower()
    for excluded in ("payment", "oauth", "wecom", "media", "openclaw", "timer", "outbound"):
        if excluded not in excluded_text:
            blockers.append(f"excluded_route_families must mention {excluded}")

    tooling = _dict(data.get("batch_tooling"))
    if tooling.get("tooling_only") is not True:
        blockers.append("batch_tooling.tooling_only must be true")
    if tooling.get("runtime_gate_modified") is not False:
        blockers.append("batch_tooling.runtime_gate_modified must be false")
    if tooling.get("disabled_by_default") is not True:
        blockers.append("batch_tooling.disabled_by_default must be true")

    per_route = _list(data.get("per_route"))
    if {str(item.get("route_family")) for item in per_route if isinstance(item, dict)} != SELECTED:
        blockers.append("per_route must exactly cover selected route families")
    for item in per_route:
        if not isinstance(item, dict):
            continue
        if item.get("owner_switch_execution_authorized_default") is not False:
            blockers.append(f"{item.get('route_family')}.owner_switch_execution_authorized_default must be false")
        for key in ("fallback_retained", "production_compat_unchanged", "shadow_compare_required", "rollback_required", "execution_forbidden", "outbound_send_forbidden"):
            if item.get(key) is not True:
                blockers.append(f"{item.get('route_family')}.{key} must be true")

    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "phase_6e_internal_owner_switch_acceptance_bundle":
        blockers.append("next_bundle.recommended_next_step must point to Phase 6E")
    for key in ("owner_switch_execution_allowed_default", "production_compat_change_allowed", "fallback_removal_allowed"):
        if next_bundle.get(key) is not False:
            blockers.append(f"next_bundle.{key} must be false")

    runner_report = _run_runner()
    details["runner"] = runner_report
    if runner_report.get("overall") != "BLOCKED":
        blockers.append("batch runner must produce default BLOCKED evidence")
    for item in _list(runner_report.get("per_route")):
        if not isinstance(item, dict):
            continue
        for key in ("owner_switch_executed", "production_compat_changed", "fallback_removed", "timer_execution_triggered", "automation_execution_triggered", "outbound_send_triggered", "external_live_call_triggered", "destructive_migration_triggered", "delete_ready"):
            if item.get(key) is not False:
                blockers.append(f"runner {item.get('route_family')}.{key} must be false")

    if state.get("last_merged_pr") != "#761":
        blockers.append("phase_execution_state.last_merged_pr must record PR #761")
    if state.get("recommended_next_pr") != "phase_6e_internal_owner_switch_acceptance_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6E")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6D allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6D Internal Metadata Owner Switch Batch Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
