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

DOC = ROOT / "docs/development/phase_7l_final_legacy_retirement_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_7l_final_legacy_retirement_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7l_final_legacy_retirement_acceptance.py"
NEXT_ALLOWED = {
    "post_phase7_owner_approved_cleanup_track",
    "new_feature_development_under_next_architecture_rules",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7l_final_legacy_retirement_acceptance.md",
    "docs/development/phase_7l_final_legacy_retirement_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7l_final_legacy_retirement_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7l_final_legacy_retirement_acceptance.py",
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
    if data.get("bundle_type") != "phase_7l_final_legacy_retirement_acceptance_bundle":
        blockers.append("bundle_type must be phase_7l_final_legacy_retirement_acceptance_bundle")
    final = _dict(data.get("final_acceptance"))
    for key in ("phase_7_completed", "fallback_retained", "production_compat_retained", "legacy_runtime_retained", "future_cleanup_required"):
        if final.get(key) is not True:
            blockers.append(f"final_acceptance.{key} must be true")
    for key in ("broad_runtime_deletion_completed", "delete_ready"):
        if final.get(key) is not False:
            blockers.append(f"final_acceptance.{key} must be false")
    retained = _dict(data.get("retained_inventory"))
    for key in ("fallback_removal_broadly_completed", "production_compat_cleanup_broadly_completed", "legacy_runtime_deletion_completed", "delete_ready"):
        if retained.get(key) is not False:
            blockers.append(f"retained_inventory.{key} must be false")
    side_effects = _dict(data.get("side_effects"))
    for key, value in side_effects.items():
        if value is not False:
            blockers.append(f"side_effects.{key} must be false")
    autopilot = _dict(data.get("autopilot_state"))
    if autopilot.get("mark_phase_7_complete") is not True:
        blockers.append("autopilot_state.mark_phase_7_complete must be true")
    for key in ("auto_start_runtime_deletion", "auto_start_fallback_removal", "auto_start_production_compat_deletion"):
        if autopilot.get(key) is not False:
            blockers.append(f"autopilot_state.{key} must be false")
    if set(_list(data.get("next_allowed_actions"))) != NEXT_ALLOWED:
        blockers.append("next_allowed_actions must be post-Phase-7 cleanup track and new feature rules")
    outcome = _dict(data.get("outcome"))
    if outcome.get("final_acceptance_only") is not True:
        blockers.append("outcome.final_acceptance_only must be true")
    for key in ("production_behavior_changed", "fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if outcome.get(key) is not False:
            blockers.append(f"outcome.{key} must be false")
    if state.get("current_phase") != "phase_7l_final_legacy_retirement_acceptance":
        blockers.append("phase_execution_state.current_phase must be Phase 7L")
    if state.get("active_candidate") != "final_legacy_retirement_acceptance":
        blockers.append("phase_execution_state.active_candidate must be final legacy retirement acceptance")
    if state.get("last_merged_pr") != "#792":
        blockers.append("phase_execution_state.last_merged_pr must record PR #792")
    if set(_list(state.get("next_allowed_actions"))) != NEXT_ALLOWED:
        blockers.append("phase_execution_state.next_allowed_actions must contain only post-Phase-7 tracks")
    phase_state = _dict(state.get("phase7l_final_legacy_retirement_acceptance"))
    if phase_state.get("phase_7_completed") is not True:
        blockers.append("phase7l state must mark Phase 7 complete")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"phase7l state {key} must be false")
    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7L allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7L Final Legacy Retirement Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
