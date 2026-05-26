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

DOC = ROOT / "docs/development/phase_7a_legacy_retirement_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_7a_legacy_retirement_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7a_legacy_retirement_readiness.py"
NEXT_BUNDLE = "phase_7b_baseline_legacy_import_remediation_bundle"
FALSE_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "legacy_runtime_deletion_authorized",
    "destructive_migration_authorized",
    "delete_ready",
    "timer_execution_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
}
REQUIRED_DIRECT_IMPORT_BLOCKERS = {
    ("aicrm_next/automation_engine/group_ops/domain.py", 10, "wecom_ability_service.domains.tasks.private_message"),
    ("aicrm_next/integration_gateway/wecom_group_adapter.py", 97, "wecom_ability_service.wecom_client"),
    ("aicrm_next/integration_gateway/wecom_group_adapter.py", 155, "wecom_ability_service.domains.broadcast_jobs"),
}
REQUIRED_CLASSIFICATION_KEYS = {
    "safe_no_behavior_change_cleanup_candidates",
    "requires_shadow_compare_before_cleanup",
    "requires_owner_approval_before_fallback_removal",
    "deferred_until_production_owner_switch_evidence",
    "not_safe_for_phase_7_first_batch",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_7a_legacy_retirement_readiness.md",
    "docs/development/phase_7a_legacy_retirement_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7a_legacy_retirement_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7a_legacy_retirement_readiness.py",
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
    if data.get("bundle_type") != "phase_7a_legacy_retirement_readiness_bundle":
        blockers.append("bundle_type must be phase_7a_legacy_retirement_readiness_bundle")
    if data.get("route_family") != "phase_7_legacy_retirement_readiness":
        blockers.append("route_family must be phase_7_legacy_retirement_readiness")

    handoff = _dict(data.get("phase_6_handoff"))
    if handoff.get("source_pr") != "#773":
        blockers.append("phase_6_handoff.source_pr must record #773")
    for key in (
        "production_owner_switches_executed",
        "production_compat_behavior_changed",
        "fallback_removed",
        "timer_execution_default_on",
        "automation_execution_default_on",
        "outbound_send",
        "live_external_default_on",
        "destructive_migration_executed",
        "delete_ready",
    ):
        if handoff.get(key) is not False:
            blockers.append(f"phase_6_handoff.{key} must be false")

    authorizations = _dict(data.get("authorizations"))
    for key in sorted(FALSE_AUTHORIZATIONS):
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    direct_imports = _list(_dict(data.get("baseline_blockers")).get("direct_legacy_imports"))
    seen = {(str(item.get("path")), item.get("line"), str(item.get("import"))) for item in direct_imports if isinstance(item, dict)}
    missing_import_blockers = sorted(REQUIRED_DIRECT_IMPORT_BLOCKERS - seen)
    if missing_import_blockers:
        blockers.append(f"missing baseline direct legacy import blockers: {missing_import_blockers}")
    env_blockers = _list(_dict(data.get("baseline_blockers")).get("environment_blockers"))
    if not any(_dict(item).get("id") == "architecture_skill_compliance_local_yaml_dependency" for item in env_blockers):
        blockers.append("must record architecture skill compliance local yaml environment blocker")

    classification = _dict(data.get("candidate_classification"))
    missing_categories = sorted(REQUIRED_CLASSIFICATION_KEYS - set(classification))
    if missing_categories:
        blockers.append(f"candidate_classification missing categories: {missing_categories}")
    for key in REQUIRED_CLASSIFICATION_KEYS:
        if not _list(classification.get(key)):
            blockers.append(f"candidate_classification.{key} must not be empty")

    selection = _dict(data.get("phase_7b_candidate_selection"))
    if selection.get("selected_next_bundle") != NEXT_BUNDLE:
        blockers.append("phase_7b_candidate_selection.selected_next_bundle must select Phase 7B")
    for key in ("behavior_change_allowed", "fallback_removal_allowed", "production_compat_change_allowed", "legacy_runtime_deletion_allowed"):
        if selection.get(key) is not False:
            blockers.append(f"phase_7b_candidate_selection.{key} must be false")
    if _list(data.get("next")) != [NEXT_BUNDLE]:
        blockers.append("next must only recommend Phase 7B")

    if state.get("current_phase") != "phase_7a_legacy_retirement_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 7A")
    if state.get("active_candidate") != "phase_7_legacy_retirement_readiness":
        blockers.append("phase_execution_state.active_candidate must be phase_7_legacy_retirement_readiness")
    if state.get("last_merged_pr") != "#773":
        blockers.append("phase_execution_state.last_merged_pr must record PR #773")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7B")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7B")
    phase_state = _dict(state.get("phase7a_legacy_retirement_readiness"))
    if phase_state.get("fallback_removal_authorized") is not False:
        blockers.append("phase7a state fallback_removal_authorized must be false")
    if phase_state.get("production_compat_behavior_change_authorized") is not False:
        blockers.append("phase7a state production_compat_behavior_change_authorized must be false")
    if phase_state.get("legacy_runtime_deletion_authorized") is not False:
        blockers.append("phase7a state legacy_runtime_deletion_authorized must be false")
    if phase_state.get("delete_ready") is not False:
        blockers.append("phase7a state delete_ready must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7A allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7A Legacy Retirement Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
