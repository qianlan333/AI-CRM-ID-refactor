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

DOC = ROOT / "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7j_legacy_runtime_cleanup_blocker_acceptance.py"
NEXT_BUNDLE = "phase_7k_final_route_ownership_manifest_cleanup_bundle"
FALSE_AUTHORIZATIONS = {
    "legacy_runtime_deletion_authorized",
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "destructive_migration_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.md",
    "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7j_legacy_runtime_cleanup_blocker_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7j_legacy_runtime_cleanup_blocker_acceptance.py",
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
    if data.get("bundle_type") != "phase_7j_legacy_runtime_cleanup_blocker_acceptance_bundle":
        blockers.append("bundle_type must be phase_7j_legacy_runtime_cleanup_blocker_acceptance_bundle")
    for key in FALSE_AUTHORIZATIONS:
        if _dict(data.get("authorizations")).get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")
    accepted = _dict(data.get("accepted_results"))
    for key in (
        "fallback_removal_occurred",
        "production_compat_behavior_changed",
        "legacy_runtime_deletion_occurred",
        "safe_runtime_cleanup_candidate_selected",
        "delete_ready",
    ):
        if accepted.get(key) is not False:
            blockers.append(f"accepted_results.{key} must be false")
    for key in (
        "runtime_cleanup_blocked_because_fallback_retained",
        "runtime_cleanup_blocked_because_production_compat_retained",
    ):
        if accepted.get(key) is not True:
            blockers.append(f"accepted_results.{key} must be true")
    decision = _dict(data.get("acceptance_decision"))
    if decision.get("status") != "accepted_blocked_runtime_cleanup":
        blockers.append("acceptance_decision.status must accept blocked runtime cleanup")
    if set(_list(decision.get("reason"))) != {"fallback_retained", "production_compat_retained", "no_safe_runtime_candidate"}:
        blockers.append("acceptance_decision.reason must include fallback, production_compat, and no safe candidate")
    if decision.get("future_cleanup_track_required") is not True:
        blockers.append("future_cleanup_track_required must be true")
    if not _list(data.get("future_evidence_required")):
        blockers.append("future_evidence_required must not be empty")
    if not _list(data.get("deferred_cleanup_candidates")):
        blockers.append("deferred_cleanup_candidates must not be empty")
    outcome = _dict(data.get("outcome"))
    if outcome.get("blocker_acceptance_only") is not True:
        blockers.append("outcome.blocker_acceptance_only must be true")
    for key in ("production_behavior_changed", "fallback_removed", "production_compat_behavior_changed", "legacy_runtime_deleted", "wildcard_cleanup", "delete_ready"):
        if outcome.get(key) is not False:
            blockers.append(f"outcome.{key} must be false")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7K")
    if state.get("current_phase") != "phase_7j_legacy_runtime_cleanup_blocker_acceptance":
        blockers.append("phase_execution_state.current_phase must be Phase 7J")
    if state.get("active_candidate") != "legacy_runtime_cleanup_blocker_acceptance":
        blockers.append("phase_execution_state.active_candidate must be legacy_runtime_cleanup_blocker_acceptance")
    if state.get("last_merged_pr") != "#790":
        blockers.append("phase_execution_state.last_merged_pr must record PR #790")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7K")
    phase_state = _dict(state.get("phase7j_legacy_runtime_cleanup_blocker_acceptance"))
    if phase_state.get("runtime_cleanup_blocked") is not True:
        blockers.append("phase7j state must record blocked runtime cleanup")
    for key in ("fallback_removed", "production_compat_behavior_changed", "wildcard_cleanup", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"phase7j state {key} must be false")
    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7J allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7J Runtime Cleanup Blocker Acceptance Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
