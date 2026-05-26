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

DOC = ROOT / "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.yaml"
RUNNER = ROOT / "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py"
CLEANUP = ROOT / "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py"
NEXT_BUNDLE = "phase_5aj_openclaw_mcp_ai_assist_family_acceptance_bundle"
COMPLETED_STEP = "phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness_completed"
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.md",
    "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
    "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup.py",
    "tools/check_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "openai", "anthropic"}
FORBIDDEN_CALLS = {"send", "run_due", "execute_due", "dispatch"}


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
            func = node.func
            calls.add(func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else "")
    return imports, calls


def _static(path: Path) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8").lower()
    imports, calls = _imports_calls(path)
    if FORBIDDEN_IMPORTS & imports:
        blockers.append(f"{path.name} imports forbidden modules: {sorted(FORBIDDEN_IMPORTS & imports)}")
    if FORBIDDEN_CALLS & calls:
        blockers.append(f"{path.name} calls forbidden names: {sorted(FORBIDDEN_CALLS & calls)}")
    for token in ("api.openai.com", "deepseek.com", "openclaw_service", "mcp_runtime_delegate", "external_agent.orchestrate", "prompt_raw_output_allowed\": true", "credential_output_allowed\": true"):
        if token in text:
            blockers.append(f"{path.name} contains forbidden token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, RUNNER, CLEANUP, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    auth = _dict(data.get("authorizations"))
    if auth.get("production_canary_tooling_authorized") is not True:
        blockers.append("production_canary_tooling_authorized must be true")
    for key, value in auth.items():
        if key != "production_canary_tooling_authorized" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    tooling = _dict(data.get("production_canary"))
    if tooling.get("default_blocked") is not True or tooling.get("single_prompt_or_tool_only") is not True or tooling.get("batch_replay_allowed") is not False:
        blockers.append("production canary safety flags invalid")
    if tooling.get("requires_staging_evidence_json") is not True or tooling.get("requires_idempotency_key") is not True:
        blockers.append("production canary must require staging evidence and idempotency")
    required_args = {"--staging-evidence-json", "--idempotency-key", "--confirm-production-live-call", "--confirm-single-approved-target", "--confirm-redacted-evidence", "--confirm-credential-non-leakage", "--confirm-no-outbound-send", "--confirm-no-automation-execution", "--confirm-rollback-owner-approved"}
    if not required_args <= set(_list(tooling.get("required_args"))):
        blockers.append("production_canary.required_args incomplete")
    cleanup = _dict(data.get("cleanup"))
    if cleanup.get("default_blocked") is not True or cleanup.get("provider_cleanup_allowed") is not False or cleanup.get("automation_execution_allowed") is not False:
        blockers.append("cleanup safety flags invalid")
    for key, value in _dict(data.get("target_safety")).items():
        if key.endswith("_allowed") and value is not False:
            blockers.append(f"target_safety.{key} must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#747":
        blockers.append("phase_execution_state.last_merged_pr must be #747")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    for path in (RUNNER, CLEANUP):
        blockers.extend(_static(path))
        text = path.read_text(encoding="utf-8")
        for arg in ("--output-json", "--output-md"):
            if arg not in text:
                blockers.append(f"{path.name} missing {arg}")
    for arg in required_args:
        if arg not in RUNNER.read_text(encoding="utf-8"):
            blockers.append(f"production canary runner missing {arg}")
    for arg in ("--canary-evidence-json", "--confirm-cleanup-reviewed", "--confirm-no-provider-cleanup", "--confirm-no-outbound-send", "--confirm-no-automation-execution", "--confirm-no-batch-cleanup"):
        if arg not in CLEANUP.read_text(encoding="utf-8"):
            blockers.append(f"cleanup runner missing {arg}")
    doc_text = DOC.read_text(encoding="utf-8").lower()
    for claim in ("production live call enabled", "outbound send enabled", "automation execution enabled", "prompt leakage enabled", "credential leakage enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5AI allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path == "aicrm_next/main.py" or path.startswith(("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")))
    if forbidden:
        blockers.append(f"changed forbidden files: {forbidden}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AI Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
