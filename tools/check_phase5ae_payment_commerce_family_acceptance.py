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

DOC = ROOT / "docs/development/phase_5ae_payment_commerce_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5ae_payment_commerce_family_acceptance.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5ae_payment_commerce_family_acceptance.py"
NEXT_BUNDLE = "phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub_bundle"
COMPLETED_STEP = "phase_5ae_payment_commerce_family_acceptance_completed"
ALLOWED = {
    "docs/development/phase_5ae_payment_commerce_family_acceptance.md",
    "docs/development/phase_5ae_payment_commerce_family_acceptance.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase5ae_payment_commerce_family_acceptance.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5ae_payment_commerce_family_acceptance.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
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
    stages = {str(item.get("stage")) for item in _list(data.get("completed_stages")) if isinstance(item, dict) and item.get("complete") is True}
    required = {"phase_5z_contract_fake_stub", "phase_5aa_live_adapter_behind_flag", "phase_5ab_staging_sandbox_canary_evidence", "phase_5ac_production_canary_readiness", "phase_5ad_production_canary_tooling"}
    if not required <= stages:
        blockers.append("completed_stages missing payment family stages")
    matrix = _dict(data.get("capability_matrix"))
    for key in ("adapter_contract_complete", "fake_stub_complete", "live_adapter_behind_flag_complete", "staging_sandbox_canary_gate_complete", "production_canary_readiness_complete", "production_canary_tooling_complete", "cleanup_runner_complete"):
        if matrix.get(key) is not True:
            blockers.append(f"capability_matrix.{key} must be true")
    for key in ("real_payment_capture_executed", "real_refund_executed", "real_settlement_executed", "production_payment_webhook_cutover_executed", "production_order_state_mutation_executed", "route_owner_switched", "fallback_removed", "production_compat_changed", "outbound_send_enabled"):
        if matrix.get(key) is not False:
            blockers.append(f"capability_matrix.{key} must be false")
    decision = _dict(data.get("acceptance_decision"))
    if decision.get("status") not in set(_list(decision.get("allowed_values"))):
        blockers.append("acceptance decision invalid")
    if decision.get("production_canary_passed") is not False or decision.get("real_money_movement_occurred") is not False:
        blockers.append("production canary and money movement must remain false")
    if _dict(data.get("next_family")).get("selected_next_bundle") != NEXT_BUNDLE:
        blockers.append(f"next_family must select {NEXT_BUNDLE}")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if state.get("last_merged_pr") != "#743":
        blockers.append("phase_execution_state.last_merged_pr must be #743")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("real payment capture enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AE allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path == "aicrm_next/main.py" or path.startswith(("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AE Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
