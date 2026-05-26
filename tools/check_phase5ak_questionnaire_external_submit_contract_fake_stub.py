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

DOC = ROOT / "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.md"
PLAN_YAML = ROOT / "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.yaml"
ADAPTER = ROOT / "aicrm_next/questionnaire/external_submit_adapter.py"
STAGING = ROOT / "tools/run_phase5ak_questionnaire_external_submit_fake_stub_staging_smoke.py"
PROD = ROOT / "tools/run_phase5ak_questionnaire_external_submit_fake_stub_production_dry_run.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5ak_questionnaire_external_submit_contract_fake_stub.py"
NEXT_BUNDLE = "phase_5al_questionnaire_external_submit_live_adapter_behind_flag_bundle"
COMPLETED_STEP = "phase_5ak_questionnaire_external_submit_contract_fake_stub_completed"
ALLOWED = {
    "aicrm_next/questionnaire/external_submit_adapter.py",
    "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.md",
    "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5ak_questionnaire_external_submit_fake_stub_staging_smoke.py",
    "tools/run_phase5ak_questionnaire_external_submit_fake_stub_production_dry_run.py",
    "tools/check_phase5ak_questionnaire_external_submit_contract_fake_stub.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5ak_questionnaire_external_submit_contract_fake_stub.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "urllib"}


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
    if FORBIDDEN_IMPORTS & _imports(path):
        blockers.append(f"{path.name} imports forbidden network module")
    for token in ("production_public_submit_write_executed\": true", "production_identity_write_executed\": true", "production_tag_write_executed\": true", "outbound_send_executed\": true", "live_oauth_callback_cutover_executed\": true"):
        if token in text:
            blockers.append(f"{path.name} contains forbidden token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, ADAPTER, STAGING, PROD, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    methods = {item for item in _list(_dict(data.get("adapter_contract")).get("methods"))}
    required_methods = {"deterministic_fake_public_submission", "validate_external_submit", "dry_run_public_submit", "dry_run_identity_mapping", "dry_run_tag_writeback"}
    if not required_methods <= methods:
        blockers.append("adapter_contract.methods incomplete")
    fake = _dict(data.get("fake_stub_contract"))
    for key in ("deterministic_submission_required", "external_userid_redaction_required", "openid_redaction_required", "unionid_redaction_required"):
        if fake.get(key) is not True:
            blockers.append(f"fake_stub_contract.{key} must be true")
    for key in ("network_call_allowed", "db_write_allowed", "production_success_claim_allowed"):
        if fake.get(key) is not False:
            blockers.append(f"fake_stub_contract.{key} must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#749":
        blockers.append("phase_execution_state.last_merged_pr must be #749")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (ADAPTER, STAGING, PROD):
        blockers.extend(_static(path))
        text = path.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if path in (STAGING, PROD) and arg not in text:
                blockers.append(f"{path.name} missing {arg}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("production public submit write enabled", "production identity write enabled", "production tag write enabled", "live oauth callback cutover enabled", "outbound send enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AK allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path == "aicrm_next/main.py" or path.startswith(("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AK Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
