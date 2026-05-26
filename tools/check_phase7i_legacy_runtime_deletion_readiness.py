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

DOC = ROOT / "docs/development/phase_7i_legacy_runtime_deletion_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_7i_legacy_runtime_deletion_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7i_legacy_runtime_deletion_readiness.py"
NEXT_BUNDLE = "phase_7j_legacy_runtime_cleanup_blocker_acceptance_bundle"
SELECTED_CANDIDATE = "none"
FALSE_AUTHORIZATIONS = {
    "legacy_runtime_deletion_authorized",
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "delete_ready",
    "destructive_migration_authorized",
}
REQUIRED_CATEGORIES = {
    "safe_to_delete_candidate",
    "needs_more_evidence",
    "unsafe_to_delete",
    "deferred_until_fallback_removed",
    "deferred_until_production_compat_cleanup",
    "deferred_due_to_external_side_effect",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7i_legacy_runtime_deletion_readiness.md",
    "docs/development/phase_7i_legacy_runtime_deletion_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7i_legacy_runtime_deletion_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7i_legacy_runtime_deletion_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = (
    "aicrm_next/automation_engine/",
    "aicrm_next/production_compat/",
    "aicrm_next/integration_gateway/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "nginx/",
    "systemd/",
)
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
    if data.get("bundle_type") != "phase_7i_legacy_runtime_deletion_readiness_bundle":
        blockers.append("bundle_type must be phase_7i_legacy_runtime_deletion_readiness_bundle")
    if data.get("selected_runtime_cleanup_candidate") != SELECTED_CANDIDATE:
        blockers.append("selected_runtime_cleanup_candidate must be none")
    for key in FALSE_AUTHORIZATIONS:
        if _dict(data.get("authorizations")).get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    evidence = _dict(data.get("evidence"))
    for key in (
        "phase_7g_fallback_removal_blocked",
        "phase_7h_production_compat_cleanup_blocked",
        "fallback_still_referenced",
        "production_compat_still_referenced",
        "route_ownership_manifest_reviewed",
        "import_graph_summary_created",
        "test_usage_matrix_created",
        "high_risk_external_runtime_present",
    ):
        if evidence.get(key) is not True:
            blockers.append(f"evidence.{key} must be true")
    for key in ("phase_7g_fallback_removal_executed", "phase_7h_production_compat_cleanup_executed"):
        if evidence.get(key) is not False:
            blockers.append(f"evidence.{key} must be false")

    matrix = _dict(data.get("delete_candidate_matrix"))
    missing_categories = sorted(REQUIRED_CATEGORIES - set(matrix))
    if missing_categories:
        blockers.append(f"delete_candidate_matrix missing categories: {missing_categories}")
    if _list(matrix.get("safe_to_delete_candidate")):
        blockers.append("safe_to_delete_candidate must be empty until fallback and production_compat blockers clear")
    for key in ("unsafe_to_delete", "deferred_until_fallback_removed", "deferred_until_production_compat_cleanup"):
        if not _list(matrix.get(key)):
            blockers.append(f"delete_candidate_matrix.{key} must not be empty")

    outcome = _dict(data.get("outcome"))
    if outcome.get("readiness_only") is not True:
        blockers.append("outcome.readiness_only must be true")
    if outcome.get("runtime_cleanup_blocked") is not True:
        blockers.append("outcome.runtime_cleanup_blocked must be true")
    for key in (
        "legacy_runtime_deletion_executed",
        "safe_runtime_cleanup_candidate_selected",
        "fallback_removed",
        "production_compat_behavior_changed",
        "wildcard_cleanup",
        "delete_ready",
    ):
        if outcome.get(key) is not False:
            blockers.append(f"outcome.{key} must be false")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7J blocker acceptance")

    if state.get("current_phase") != "phase_7i_legacy_runtime_deletion_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 7I")
    if state.get("active_candidate") != "legacy_runtime_deletion_readiness":
        blockers.append("phase_execution_state.active_candidate must be legacy_runtime_deletion_readiness")
    if state.get("last_merged_pr") != "#789":
        blockers.append("phase_execution_state.last_merged_pr must record PR #789")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7J blocker acceptance")
    phase_state = _dict(state.get("phase7i_legacy_runtime_deletion_readiness"))
    if phase_state.get("runtime_cleanup_blocked") is not True:
        blockers.append("phase7i state must record blocked runtime cleanup")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"phase7i state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7I allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7I Legacy Runtime Deletion Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
