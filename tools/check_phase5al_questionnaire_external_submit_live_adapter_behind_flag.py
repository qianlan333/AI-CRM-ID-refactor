#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.yaml"
ADAPTER = ROOT / "aicrm_next/questionnaire/external_submit_live_adapter.py"
GATEWAY = ROOT / "aicrm_next/questionnaire/external_submit_live_gateway.py"
STAGING = ROOT / "tools/run_phase5al_questionnaire_external_submit_live_staging_evidence.py"
PROD = ROOT / "tools/run_phase5al_questionnaire_external_submit_live_production_dry_run_gate.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py"
NEXT_BUNDLE = "phase_5am_questionnaire_external_submit_staging_canary_evidence_bundle"
COMPLETED_STEP = "phase_5al_questionnaire_external_submit_live_adapter_behind_flag_completed"
ALLOWED = {
    "aicrm_next/questionnaire/external_submit_live_adapter.py",
    "aicrm_next/questionnaire/external_submit_live_gateway.py",
    "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.md",
    "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5al_questionnaire_external_submit_live_staging_evidence.py",
    "tools/run_phase5al_questionnaire_external_submit_live_production_dry_run_gate.py",
    "tools/check_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py",
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

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports

def _static(path: Path) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8").lower()
    if {"requests", "httpx", "aiohttp"} & _imports(path):
        blockers.append(f"{path.name} imports network module")
    for token in ("production_public_submit_write_executed\": true", "production_identity_write_executed\": true", "production_tag_write_executed\": true", "outbound_send_executed\": true", "live_oauth_callback_cutover_executed\": true"):
        if token in text:
            blockers.append(f"{path.name} contains forbidden token: {token}")
    return blockers

def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, ADAPTER, GATEWAY, STAGING, PROD, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    auth = _dict(data.get("authorizations"))
    if auth.get("live_adapter_code_authorized") is not True:
        blockers.append("live_adapter_code_authorized must be true")
    for key, value in auth.items():
        if key != "live_adapter_code_authorized" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    if _dict(data.get("live_adapter")).get("default_enabled") is not False:
        blockers.append("live adapter must default disabled")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#750":
        blockers.append("phase_execution_state.last_merged_pr must be #750")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (ADAPTER, GATEWAY, STAGING, PROD):
        blockers.extend(_static(path))
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AL allowlist: {unexpected}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}

def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AL Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")

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
