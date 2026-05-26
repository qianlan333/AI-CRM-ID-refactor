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

DOC = ROOT / "docs/development/phase_7c_delete_ready_candidate_selection.md"
PLAN_YAML = ROOT / "docs/development/phase_7c_delete_ready_candidate_selection.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7c_delete_ready_candidate_selection.py"
NEXT_BUNDLE = "phase_7d_first_safe_cleanup_bundle"
REQUIRED_CATEGORIES = {
    "docs_tooling_state_cleanup_candidates",
    "obsolete_phase_artifacts_archive_candidates",
    "exact_route_fallback_cleanup_candidates",
    "production_compat_manifest_cleanup_candidates",
    "legacy_runtime_deletion_candidates",
    "unsafe_deferred_candidates",
}
FALSE_AUTHORIZATIONS = {
    "delete_ready_authorized",
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "legacy_runtime_deletion_authorized",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7c_delete_ready_candidate_selection.md",
    "docs/development/phase_7c_delete_ready_candidate_selection.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7c_delete_ready_candidate_selection.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7c_delete_ready_candidate_selection.py",
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


def _candidate_items(categories: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value in categories.values():
        for item in _list(value):
            if isinstance(item, dict):
                items.append(item)
    return items


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
    if data.get("bundle_type") != "phase_7c_delete_ready_candidate_selection_bundle":
        blockers.append("bundle_type must be phase_7c_delete_ready_candidate_selection_bundle")
    if data.get("cleanup_family") != "delete_ready_candidate_selection":
        blockers.append("cleanup_family must be delete_ready_candidate_selection")

    authorizations = _dict(data.get("authorizations"))
    for key in FALSE_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    categories = _dict(data.get("candidate_categories"))
    missing = sorted(REQUIRED_CATEGORIES - set(categories))
    if missing:
        blockers.append(f"candidate_categories missing {missing}")
    for key in REQUIRED_CATEGORIES:
        if not _list(categories.get(key)):
            blockers.append(f"candidate_categories.{key} must not be empty")
    items = _candidate_items(categories)
    required_fields = {
        "candidate_id",
        "file_or_route_family",
        "cleanup_type",
        "required_evidence",
        "behavior_change_expected",
        "rollback_strategy",
        "owner_approval_required",
        "delete_ready_candidate",
        "delete_ready_authorized",
    }
    for item in items:
        missing_fields = sorted(required_fields - set(item))
        if missing_fields:
            blockers.append(f"candidate {item.get('candidate_id')} missing fields {missing_fields}")
        if item.get("delete_ready_authorized") is not False:
            blockers.append(f"candidate {item.get('candidate_id')} must keep delete_ready_authorized false")
    if not any(item.get("behavior_change_expected") is False and item.get("owner_approval_required") is False for item in items):
        blockers.append("must include at least one no-behavior-change candidate")
    if not any(item.get("owner_approval_required") is True for item in items):
        blockers.append("must include owner-approval-required candidates")

    selected = _dict(data.get("phase_7d_first_cleanup_candidate"))
    if selected.get("selected_candidate_id") != "legacy_import_checker_baseline_followup":
        blockers.append("Phase 7D first candidate must select legacy_import_checker_baseline_followup")
    for key in ("fallback_removal_allowed", "production_compat_behavior_change_allowed", "legacy_runtime_deletion_allowed", "delete_ready_authorized"):
        if selected.get(key) is not False:
            blockers.append(f"phase_7d_first_cleanup_candidate.{key} must be false")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7D")

    if state.get("current_phase") != "phase_7c_delete_ready_candidate_selection":
        blockers.append("phase_execution_state.current_phase must be Phase 7C")
    if state.get("active_candidate") != "phase_7_delete_ready_candidate_selection":
        blockers.append("phase_execution_state.active_candidate must be phase_7_delete_ready_candidate_selection")
    if state.get("last_merged_pr") != "#775":
        blockers.append("phase_execution_state.last_merged_pr must record PR #775")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7D")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7D")
    phase_state = _dict(state.get("phase7c_delete_ready_candidate_selection"))
    if phase_state.get("delete_ready_authorized") is not False:
        blockers.append("phase7c state delete_ready_authorized must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7C allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7C Delete Ready Candidate Selection Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
