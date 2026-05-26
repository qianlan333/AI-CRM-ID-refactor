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


DOC = ROOT / "docs/development/phase_5t_oauth_identity_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5t_oauth_identity_family_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5t_oauth_identity_family_acceptance.py"
NEXT_BUNDLE = "phase_5u_media_upload_adapter_contract_fake_stub_bundle"
COMPLETED_STEP = "phase_5t_oauth_identity_family_acceptance_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5t_oauth_identity_family_acceptance.md",
    "docs/development/phase_5t_oauth_identity_family_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase5t_oauth_identity_family_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5t_oauth_identity_family_acceptance.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "deploy/", "nginx/", "systemd/", "migrations/")
FORBIDDEN_EXACT = {"aicrm_next/main.py"}
FORBIDDEN_DOC_CLAIMS = {
    "wider rollout enabled",
    "route owner switched",
    "fallback removed",
    "production_compat changed",
    "delete_ready true",
    "delete_ready: true",
    "production canary passed",
    "production callback cutover enabled",
    "production session write enabled",
    "production identity write enabled",
    "token persistence enabled",
}


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {line.strip() for line in proc.stdout.splitlines() if proc.returncode == 0 and line.strip()}


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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()
    if data.get("status") != "phase_5t_oauth_identity_family_acceptance_no_new_live_call":
        blockers.append("status mismatch")
    if data.get("bundle_type") != "phase_5_external_adapter_family_acceptance_bundle":
        blockers.append("bundle_type mismatch")
    if data.get("route_family") != "/api/h5/wechat/oauth*":
        blockers.append("route_family must be /api/h5/wechat/oauth*")
    auth = _dict(data.get("authorizations"))
    for key, value in auth.items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    expected_stages = {
        "phase_5n_contract",
        "phase_5o_fake_stub_runtime",
        "phase_5p_live_adapter_behind_flag",
        "phase_5q_staging_live_canary_gate",
        "phase_5r_production_canary_readiness",
        "phase_5s_production_live_canary_tooling",
    }
    stages = _list(data.get("completed_stages"))
    actual_stages = {str(item.get("stage")) for item in stages if isinstance(item, dict) and item.get("complete") is True}
    if expected_stages - actual_stages:
        blockers.append(f"completed_stages missing: {sorted(expected_stages - actual_stages)}")

    matrix = _dict(data.get("capability_matrix"))
    for key in (
        "adapter_contract_complete",
        "fake_stub_complete",
        "live_adapter_behind_flag_complete",
        "staging_canary_gate_complete",
        "production_canary_readiness_complete",
        "production_live_canary_tooling_complete",
        "cleanup_runner_complete",
    ):
        if matrix.get(key) is not True:
            blockers.append(f"capability_matrix.{key} must be true")
    for key in (
        "production_canary_passed",
        "production_callback_cutover_enabled",
        "production_session_write_enabled",
        "production_identity_write_enabled",
        "token_persistence_enabled",
        "route_owner_switched",
        "fallback_removed",
        "production_compat_changed",
        "batch_replay_enabled",
        "outbound_send_enabled",
    ):
        if matrix.get(key) is not False:
            blockers.append(f"capability_matrix.{key} must be false")

    decision = _dict(data.get("acceptance_decision"))
    if decision.get("status") not in set(_list(decision.get("allowed_values"))):
        blockers.append("acceptance_decision.status must be an allowed value")
    if decision.get("status") != "accepted_with_blocked_evidence_only":
        blockers.append("acceptance_decision.status must be accepted_with_blocked_evidence_only without verified production canary evidence")
    if decision.get("production_canary_passed") is not False:
        blockers.append("acceptance_decision.production_canary_passed must be false")
    if decision.get("wider_rollout_authorized") is not False:
        blockers.append("acceptance_decision.wider_rollout_authorized must be false")

    rollout = _dict(data.get("rollout_boundary"))
    for key, value in rollout.items():
        if key.endswith("_deferred") and value is not True:
            blockers.append(f"rollout_boundary.{key} must be true")
        if key in {"wider_rollout_authorized", "delete_ready"} and value is not False:
            blockers.append(f"rollout_boundary.{key} must be false")

    next_family = _dict(data.get("next_family"))
    if next_family.get("selected_next_bundle") != NEXT_BUNDLE:
        blockers.append(f"next_family.selected_next_bundle must be {NEXT_BUNDLE}")
    if next_family.get("route_family") != "/api/admin/image-library*":
        blockers.append("next_family.route_family must be /api/admin/image-library*")
    if next_family.get("capability_owner") != "aicrm_next.media_library":
        blockers.append("next_family.capability_owner must be aicrm_next.media_library")
    if next_family.get("live_external_call_allowed") is not False:
        blockers.append("next_family.live_external_call_allowed must be false")
    if not _list(next_family.get("required_guardrails")):
        blockers.append("next_family.required_guardrails must be present")

    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")

    if state.get("last_merged_pr") != "#732":
        blockers.append("phase_execution_state.last_merged_pr must be #732")
    if state.get("last_attempted_action") != "phase_5t_oauth_identity_family_acceptance_bundle":
        blockers.append("last_attempted_action must be Phase 5T")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if state.get("active_candidate") != "/api/admin/image-library*":
        blockers.append("active_candidate must select the media image-library route family")
    if state.get("capability_owner") != "aicrm_next.media_library":
        blockers.append("capability_owner must be aicrm_next.media_library")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")

    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc must not claim forbidden state: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5T allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"forbidden changed files: {forbidden}")

    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5T Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
