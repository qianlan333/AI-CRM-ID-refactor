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

DOC = ROOT / "docs/development/phase_5_aggregate_acceptance_review.md"
PLAN_YAML = ROOT / "docs/development/phase_5_aggregate_acceptance_review.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5_aggregate_acceptance_review.py"
COMPLETED_STEP = "phase_5_aggregate_acceptance_review_completed"
ALLOWED = {
    "docs/development/phase_5_aggregate_acceptance_review.md",
    "docs/development/phase_5_aggregate_acceptance_review.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase5_aggregate_acceptance_review.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5_aggregate_acceptance_review.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
REQUIRED_FAMILIES = {
    "wecom_tags",
    "wecom_customer_contact_callback",
    "oauth_identity",
    "media_upload",
    "payment_commerce",
    "openclaw_mcp_ai_assist",
    "questionnaire_external_submit",
}


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {line.strip() for line in proc.stdout.splitlines() if proc.returncode == 0 and line.strip()}


def _changed_files() -> set[str]:
    return set().union(_run_git(["diff", "--name-only", "origin/main...HEAD"]), _run_git(["diff", "--name-only"]), _run_git(["diff", "--name-only", "--cached"]), _run_git(["ls-files", "--others", "--exclude-standard"]))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    families = _list(data.get("families"))
    present = {str(item.get("family")) for item in families if isinstance(item, dict)}
    if REQUIRED_FAMILIES != present:
        blockers.append("families must exactly cover selected Phase 5 families")
    for item in families:
        if not isinstance(item, dict):
            continue
        if item.get("family_acceptance_complete") is not True:
            blockers.append(f"{item.get('family')}.family_acceptance_complete must be true")
        for key in ("production_canary_passed", "owner_switched", "fallback_removed", "production_compat_changed"):
            if item.get(key) is not False:
                blockers.append(f"{item.get('family')}.{key} must be false")
    matrix = _dict(data.get("aggregate_matrix"))
    for key in ("all_selected_families_acceptance_complete", "live_capabilities_remain_behind_explicit_gates", "production_owner_switch_deferred_to_phase_6", "fallback_removal_deferred_to_phase_7", "production_compat_narrowing_deferred_to_phase_6_or_7"):
        if matrix.get(key) is not True:
            blockers.append(f"aggregate_matrix.{key} must be true")
    for key in ("delete_ready", "wider_rollout_authorized", "default_live_external_call_enabled", "outbound_send_enabled", "timer_or_automation_execution_enabled"):
        if matrix.get(key) is not False:
            blockers.append(f"aggregate_matrix.{key} must be false")
    for section in ("phase6_readiness", "phase7_deferral", "business_continuity"):
        for key, value in _dict(data.get(section)).items():
            if value is not True:
                blockers.append(f"{section}.{key} must be true")
    if state.get("last_merged_pr") != "#755":
        blockers.append("phase_execution_state.last_merged_pr must be #755")
    if state.get("recommended_next_pr") != "none_phase_5_complete":
        blockers.append("phase_execution_state.recommended_next_pr must be none_phase_5_complete")
    if _list(state.get("next_allowed_actions")) != []:
        blockers.append("next_allowed_actions must be empty after aggregate acceptance")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("owner switch authorized", "fallback removal authorized", "production_compat change authorized", "default-on live external call", "outbound send enabled", "automation execution enabled", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED)
    if unexpected:
        blockers.append(f"changed files outside Phase 5 aggregate allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path == "aicrm_next/main.py" or path.startswith(("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5 Aggregate Acceptance Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
