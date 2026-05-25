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

DOC = ROOT / "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5m_wecom_customer_contact_callback_family_acceptance.py"
NEXT_BUNDLE = "phase_5n_oauth_identity_adapter_contract_bundle"
COMPLETED_STEP = "phase_5m_wecom_customer_contact_callback_family_acceptance_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.md",
    "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase5m_wecom_customer_contact_callback_family_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5m_wecom_customer_contact_callback_family_acceptance.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
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
    auth = _dict(data.get("authorizations"))
    for key, value in auth.items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    stages = _list(data.get("completed_stages"))
    expected = {"phase_5h_contract", "phase_5i_fake_stub_runtime", "phase_5j_live_callback_behind_flag", "phase_5k_staging_live_callback_canary_gate", "phase_5l_production_callback_canary_readiness"}
    actual = {str(item.get("stage")) for item in stages if isinstance(item, dict) and item.get("complete") is True}
    if expected - actual:
        blockers.append(f"completed_stages missing: {sorted(expected - actual)}")
    matrix = _dict(data.get("capability_matrix"))
    for key in ("production_callback_cutover_enabled", "route_owner_switched", "fallback_removed", "production_compat_changed", "batch_customer_sync_enabled", "outbound_send_enabled"):
        if matrix.get(key) is not False:
            blockers.append(f"capability_matrix.{key} must be false")
    decision = _dict(data.get("acceptance_decision"))
    if decision.get("status") != "accepted_with_blocked_evidence_only":
        blockers.append("acceptance_decision.status must be accepted_with_blocked_evidence_only")
    if decision.get("production_callback_canary_passed") is not False:
        blockers.append("production_callback_canary_passed must be false")
    rollout = _dict(data.get("rollout_boundary"))
    for key, value in rollout.items():
        if key.endswith("_deferred") and value is not True:
            blockers.append(f"rollout_boundary.{key} must be true")
        if key in {"wider_rollout_authorized", "delete_ready"} and value is not False:
            blockers.append(f"rollout_boundary.{key} must be false")
    next_family = _dict(data.get("next_family"))
    if next_family.get("selected_next_bundle") != NEXT_BUNDLE:
        blockers.append(f"next_family.selected_next_bundle must be {NEXT_BUNDLE}")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if state.get("last_merged_pr") != "#725":
        blockers.append("phase_execution_state.last_merged_pr must be #725")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5M allowlist: {unexpected}")
    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5M Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
