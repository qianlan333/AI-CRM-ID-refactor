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
from tools.check_legacy_facade_growth_freeze import build_report as legacy_freeze_report
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_7d_first_safe_cleanup.md"
PLAN_YAML = ROOT / "docs/development/phase_7d_first_safe_cleanup.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7d_first_safe_cleanup.py"
NEXT_BUNDLE = "phase_7e_fallback_cleanup_readiness_bundle"
EXPECTED_RECOMMENDATION = "READY_FOR_PHASE7_BASELINE_IMPORT_CLEANUP_ACCEPTANCE"
FALSE_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "legacy_runtime_deletion_authorized",
    "destructive_migration_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7d_first_safe_cleanup.md",
    "docs/development/phase_7d_first_safe_cleanup.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_legacy_facade_growth_freeze.py",
    "tools/check_phase7d_first_safe_cleanup.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7d_first_safe_cleanup.py",
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
    cleanup = _dict(data.get("cleanup"))
    if data.get("bundle_type") != "phase_7d_first_safe_cleanup_bundle":
        blockers.append("bundle_type must be phase_7d_first_safe_cleanup_bundle")
    if cleanup.get("new_recommendation") != EXPECTED_RECOMMENDATION:
        blockers.append("cleanup.new_recommendation must match expected Phase 7 baseline cleanup recommendation")
    for key in ("cleanup_behavior_change", "legacy_runtime_deleted", "delete_ready"):
        if cleanup.get(key) is not False:
            blockers.append(f"cleanup.{key} must be false")
    for key in ("production_behavior_unchanged", "fallback_retained", "production_compat_unchanged"):
        if cleanup.get(key) is not True:
            blockers.append(f"cleanup.{key} must be true")

    authorizations = _dict(data.get("authorizations"))
    for key in FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    legacy_report = legacy_freeze_report(ROOT)
    details["legacy_facade_growth_freeze"] = legacy_report
    if legacy_report.get("overall") != "PASS":
        blockers.append(f"legacy facade growth freeze must pass: {legacy_report.get('blockers')}")
    if legacy_report.get("recommendation") != EXPECTED_RECOMMENDATION:
        blockers.append("legacy facade growth freeze recommendation not updated")

    evidence = _dict(data.get("verification_evidence"))
    if evidence.get("direct_legacy_import_blockers") != 0:
        blockers.append("direct_legacy_import_blockers must be 0")
    for key in ("runtime_files_changed", "route_behavior_changed", "deploy_config_changed"):
        if evidence.get(key) is not False:
            blockers.append(f"verification_evidence.{key} must be false")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7E")

    if state.get("current_phase") != "phase_7d_first_safe_cleanup":
        blockers.append("phase_execution_state.current_phase must be Phase 7D")
    if state.get("active_candidate") != "phase_7_first_safe_cleanup":
        blockers.append("phase_execution_state.active_candidate must be phase_7_first_safe_cleanup")
    if state.get("last_merged_pr") != "#776":
        blockers.append("phase_execution_state.last_merged_pr must record PR #776")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7E")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7E")
    phase_state = _dict(state.get("phase7d_first_safe_cleanup"))
    if phase_state.get("delete_ready") is not False:
        blockers.append("phase7d state delete_ready must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7D allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7D First Safe Cleanup Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
