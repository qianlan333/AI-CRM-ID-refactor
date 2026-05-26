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

DOC = ROOT / "docs/development/phase_6a_owner_production_compat_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_6a_owner_production_compat_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6a_owner_production_compat_readiness.py"

REQUIRED_ALLOWED_SCOPE = {
    "owner_switch_readiness",
    "owner_switch_canary_planning",
    "production_compat_narrowing_readiness",
    "fallback_shadow_comparison",
    "rollback_path_validation",
    "route_ownership_manifest_review",
}
REQUIRED_FORBIDDEN_SCOPE = {
    "owner_switch_execution",
    "production_compat_behavior_change",
    "fallback_removal",
    "timer_execution",
    "automation_execution",
    "outbound_send",
    "delete_ready",
}
REQUIRED_CANDIDATE_FIELDS = {
    "route_family",
    "capability_owner",
    "current_phase_completion",
    "owner_switch_ready",
    "production_compat_narrowing_ready",
    "fallback_removal_ready",
    "required_evidence",
    "blockers",
    "risk_level",
    "rollback_requirement",
    "recommended_next_bundle",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6a_owner_production_compat_readiness.md",
    "docs/development/phase_6a_owner_production_compat_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6a_owner_production_compat_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6a_owner_production_compat_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT = {
    "app.py",
    "legacy_flask_app.py",
}
FORBIDDEN_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "nginx/",
    "systemd/",
)
FORBIDDEN_DOC_CLAIMS = (
    "owner switch executed",
    "fallback removed",
    "production_compat changed",
    "timer enabled",
    "execution enabled",
    "delete_ready true",
    "delete_ready: true",
)


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
    details["status"] = data.get("status")
    details["route_family"] = data.get("route_family")

    authorizations = _dict(data.get("authorizations"))
    for key, value in authorizations.items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    handoff = _dict(data.get("phase_5_handoff"))
    for key in (
        "phase_5_completed",
        "external_adapter_tooling_complete_under_gates",
        "production_owner_switch_deferred_to_phase6",
        "fallback_removal_deferred_to_phase7",
        "production_compat_narrowing_deferred_to_phase6_or_7",
    ):
        if handoff.get(key) is not True:
            blockers.append(f"phase_5_handoff.{key} must be true")
    if handoff.get("delete_ready") is not False:
        blockers.append("phase_5_handoff.delete_ready must be false")

    scope = _dict(data.get("phase_6_scope"))
    if _strings(scope.get("allowed")) != REQUIRED_ALLOWED_SCOPE:
        blockers.append("phase_6_scope.allowed must exactly match Phase 6A allowed readiness actions")
    if _strings(scope.get("forbidden_in_phase_6a")) != REQUIRED_FORBIDDEN_SCOPE:
        blockers.append("phase_6_scope.forbidden_in_phase_6a must exactly match Phase 6A forbidden actions")

    inventory = _dict(data.get("candidate_inventory"))
    if _strings(inventory.get("required_fields")) != REQUIRED_CANDIDATE_FIELDS:
        blockers.append("candidate_inventory.required_fields must exactly match required candidate fields")
    candidates = _list(inventory.get("candidates"))
    if not candidates:
        blockers.append("candidate_inventory.candidates must be non-empty")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            blockers.append(f"candidate_inventory.candidates[{index}] must be a mapping")
            continue
        missing = sorted(REQUIRED_CANDIDATE_FIELDS - set(candidate))
        if missing:
            blockers.append(f"candidate {candidate.get('route_family', index)} missing fields: {missing}")
        if candidate.get("fallback_removal_ready") is not False:
            blockers.append(f"candidate {candidate.get('route_family', index)} fallback_removal_ready must be false")

    first = _dict(data.get("first_phase6_candidate"))
    for key in ("selected_route_family", "capability_owner", "risk_level", "rollback_requirement", "next_bundle"):
        if not first.get(key):
            blockers.append(f"first_phase6_candidate.{key} must be non-empty")
    for key in ("owner_switch_execution_authorized", "production_compat_change_authorized", "fallback_removal_authorized"):
        if first.get(key) is not False:
            blockers.append(f"first_phase6_candidate.{key} must be false")
    if not _list(first.get("required_guardrails")):
        blockers.append("first_phase6_candidate.required_guardrails must be non-empty")
    if not _list(first.get("required_evidence")):
        blockers.append("first_phase6_candidate.required_evidence must be non-empty")

    recommendation = _dict(data.get("phase_6b_recommendation"))
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_6b_recommendation.recommended_next_step must be non-empty")
    if not recommendation.get("route_family"):
        blockers.append("phase_6b_recommendation.route_family must be non-empty")
    for key in ("owner_switch_execution_allowed", "production_compat_change_allowed", "fallback_removal_allowed"):
        if recommendation.get(key) is not False:
            blockers.append(f"phase_6b_recommendation.{key} must be false")

    continuity = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "legacy_fallback_retained", "production_compat_unchanged", "no_live_behavior_change"):
        if continuity.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")

    if state.get("last_merged_pr") != "#756":
        blockers.append("phase_execution_state.last_merged_pr must record PR #756")
    if state.get("recommended_next_pr") != "phase_6b_first_owner_switch_canary_plan_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6B")
    if _list(state.get("next_allowed_actions")) != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty after Phase 6A")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in FORBIDDEN_DOC_CLAIMS:
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6A allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6A Owner Production Compat Readiness Check", ""]
    lines.append(f"- overall: {report['overall']}")
    blockers = report.get("blockers") or []
    lines.append("- blockers:")
    lines.extend(f"  - {item}" for item in blockers or ["none"])
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
