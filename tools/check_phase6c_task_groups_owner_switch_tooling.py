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

DOC = ROOT / "docs/development/phase_6c_task_groups_owner_switch_tooling.md"
PLAN_YAML = ROOT / "docs/development/phase_6c_task_groups_owner_switch_tooling.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6c_task_groups_owner_switch_tooling.py"
RUNNERS = [
    ROOT / "tools/run_phase6c_task_groups_owner_switch_canary.py",
    ROOT / "tools/run_phase6c_task_groups_shadow_compare.py",
    ROOT / "tools/run_phase6c_task_groups_owner_switch_rollback.py",
]
REQUIRED_ENV = {
    "AICRM_PHASE6C_TASK_GROUPS_OWNER_SWITCH_APPROVED",
    "AICRM_PHASE6C_TASK_GROUPS_CONFIG_REVIEWED",
    "AICRM_PHASE6C_TASK_GROUPS_ROLLBACK_OWNER_APPROVED",
    "AICRM_PHASE6C_TASK_GROUPS_SHADOW_COMPARE_PASSED",
}
REQUIRED_ARGS = {
    "--confirm-owner-switch-canary",
    "--confirm-fallback-retained",
    "--confirm-production-compat-unchanged",
    "--confirm-rollback-ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6c_task_groups_owner_switch_tooling.md",
    "docs/development/phase_6c_task_groups_owner_switch_tooling.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6c_task_groups_owner_switch_tooling.py",
    "tools/run_phase6c_task_groups_owner_switch_canary.py",
    "tools/run_phase6c_task_groups_shadow_compare.py",
    "tools/run_phase6c_task_groups_owner_switch_rollback.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6c_task_groups_owner_switch_tooling.py",
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


def _strings(value: Any) -> set[str]:
    return {str(item) for item in value} if isinstance(value, list) else set()


def _run_runner(path: Path) -> dict[str, Any]:
    proc = subprocess.run([sys.executable, str(path)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return {"overall": "FAIL", "stderr": proc.stderr}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"overall": "FAIL", "stdout": proc.stdout}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST, *RUNNERS):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("route_family") != "/api/admin/automation-conversion/task-groups*":
        blockers.append("route_family must be /api/admin/automation-conversion/task-groups*")
    tooling = _dict(data.get("tooling"))
    if tooling.get("runtime_gate_modified") is not False:
        blockers.append("tooling.runtime_gate_modified must be false")
    if tooling.get("tooling_only") is not True:
        blockers.append("tooling.tooling_only must be true")
    if tooling.get("disabled_by_default") is not True:
        blockers.append("tooling.disabled_by_default must be true")

    if _strings(data.get("required_env_gates")) != REQUIRED_ENV:
        blockers.append("required_env_gates must exactly match Phase 6C env gates")
    if _strings(data.get("required_args")) != REQUIRED_ARGS:
        blockers.append("required_args must exactly match Phase 6C confirmations")

    default_evidence = _dict(data.get("default_evidence"))
    if default_evidence.get("blocked_by_default") is not True:
        blockers.append("default_evidence.blocked_by_default must be true")
    for key in (
        "owner_switch_executed",
        "production_compat_changed",
        "fallback_removed",
        "timer_execution_triggered",
        "automation_execution_triggered",
        "outbound_send_triggered",
        "destructive_migration_triggered",
        "delete_ready",
    ):
        if default_evidence.get(key) is not False:
            blockers.append(f"default_evidence.{key} must be false")

    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "phase_6d_internal_metadata_owner_switch_batch_bundle":
        blockers.append("next_bundle.recommended_next_step must point to Phase 6D")
    for key in ("owner_switch_execution_allowed_default", "production_compat_change_allowed", "fallback_removal_allowed"):
        if next_bundle.get(key) is not False:
            blockers.append(f"next_bundle.{key} must be false")

    for runner in RUNNERS:
        runner_report = _run_runner(runner)
        details[runner.name] = runner_report
        if runner_report.get("overall") != "BLOCKED":
            blockers.append(f"{runner.name} must produce default BLOCKED evidence")
        for key in (
            "owner_switch_executed",
            "production_compat_changed",
            "fallback_removed",
            "timer_execution_triggered",
            "automation_execution_triggered",
            "outbound_send_triggered",
            "delete_ready",
        ):
            if runner_report.get(key) is not False:
                blockers.append(f"{runner.name}.{key} must be false")

    if state.get("last_merged_pr") != "#759":
        blockers.append("phase_execution_state.last_merged_pr must record PR #759")
    if state.get("recommended_next_pr") != "phase_6d_internal_metadata_owner_switch_batch_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6D")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6C allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6C Task Groups Owner Switch Tooling Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
