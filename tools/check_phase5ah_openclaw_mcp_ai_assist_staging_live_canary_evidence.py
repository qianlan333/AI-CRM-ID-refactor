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

DOC = ROOT / "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py"
PROD_REVIEW = ROOT / "tools/run_phase5ah_openclaw_mcp_ai_assist_production_readiness_review.py"
TEST = ROOT / "tests/test_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py"
NEXT_BUNDLE = "phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness_bundle"
COMPLETED_STEP = "phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.md",
    "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
    "tools/run_phase5ah_openclaw_mcp_ai_assist_production_readiness_review.py",
    "tools/check_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
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


def _imports_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return imports, calls


def _static_blockers(path: Path) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8").lower()
    imports, calls = _imports_calls(path)
    if imports & {"requests", "httpx", "aiohttp", "urllib", "openai", "anthropic"}:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden provider modules")
    if calls & {"send", "run_due", "execute_due", "dispatch"}:
        blockers.append(f"{path.relative_to(ROOT)} calls forbidden execution names")
    for token in ("api.openai.com", "deepseek.com", "call_deepseek", "openclaw_service", "mcp_runtime_delegate", "external_agent.orchestrate"):
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} contains forbidden token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, STAGING_RUNNER, PROD_REVIEW, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("route_family") != "/mcp":
        blockers.append("route_family must be /mcp")
    auth = _dict(data.get("authorizations"))
    if auth.get("staging_live_canary_possible_with_approval") is not True:
        blockers.append("staging_live_canary_possible_with_approval must be true")
    for key, value in auth.items():
        if key != "staging_live_canary_possible_with_approval" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    canary = _dict(data.get("staging_canary"))
    if canary.get("default_blocked") is not True or canary.get("single_target_only") is not True or canary.get("batch_replay_allowed") is not False:
        blockers.append("staging canary safety fields invalid")
    required_args = {"--execute-staging-canary", "--confirm-live-call", "--confirm-staging-only", "--confirm-approved-target", "--confirm-redaction", "--confirm-no-outbound-send", "--confirm-no-automation-execution", "--idempotency-key"}
    if not required_args <= set(_list(canary.get("required_args"))):
        blockers.append("staging_canary.required_args incomplete")
    target = _dict(data.get("target_safety"))
    for key in ("single_prompt_or_tool_only", "prompt_redaction_required", "context_redaction_required", "credential_redaction_required"):
        if target.get(key) is not True:
            blockers.append(f"target_safety.{key} must be true")
    for key in ("batch_replay_allowed", "external_mutation_allowed", "raw_prompt_output_allowed", "raw_credential_output_allowed"):
        if target.get(key) is not False:
            blockers.append(f"target_safety.{key} must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    prod = _dict(data.get("production_readiness_review"))
    for key in ("production_live_call_executed", "outbound_send_executed", "automation_execution_executed"):
        if prod.get(key) is not False:
            blockers.append(f"production_readiness_review.{key} must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#746":
        blockers.append("phase_execution_state.last_merged_pr must be #746")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (STAGING_RUNNER, PROD_REVIEW):
        blockers.extend(_static_blockers(path))
        text = path.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{path.name} missing {arg}")
    for arg in required_args:
        if arg not in STAGING_RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"staging runner missing {arg}")
    for arg in ("--staging-evidence-json", "--confirm-no-production-live-call", "--confirm-no-outbound-send", "--confirm-no-automation-execution"):
        if arg not in PROD_REVIEW.read_text(encoding="utf-8"):
            blockers.append(f"production readiness runner missing {arg}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("production live call enabled", "outbound send enabled", "automation execution enabled", "prompt leakage enabled", "credential leakage enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AH allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path == "aicrm_next/main.py" or path.startswith(("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AH Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
