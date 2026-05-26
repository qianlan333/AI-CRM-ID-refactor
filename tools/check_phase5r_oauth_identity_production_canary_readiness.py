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

DOC = ROOT / "docs/development/phase_5r_oauth_identity_production_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5r_oauth_identity_production_canary_readiness.yaml"
RUNNER = ROOT / "tools/run_phase5r_oauth_identity_production_canary_readiness.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5r_oauth_identity_production_canary_readiness.py"
NEXT_BUNDLE = "phase_5s_oauth_identity_production_live_canary_execution_bundle"
COMPLETED_STEP = "phase_5r_oauth_identity_production_canary_readiness_completed"
REQUIRED_ENV = {
    "AICRM_PHASE5R_OAUTH_IDENTITY_PRODUCTION_CANARY_PLANNING_APPROVED",
    "AICRM_PHASE5R_OAUTH_IDENTITY_PRODUCTION_CONFIG_REVIEWED",
    "AICRM_PHASE5R_OAUTH_IDENTITY_ROLLBACK_OWNER_APPROVED",
    "AICRM_PHASE5R_OAUTH_IDENTITY_CALLBACK_TARGET_POLICY_REVIEWED",
    "AICRM_PHASE5R_OAUTH_IDENTITY_TOKEN_POLICY_REVIEWED",
}
REQUIRED_ARGS = {
    "--staging-evidence-json",
    "--confirm-no-production-live-oauth-call",
    "--confirm-no-production-callback-cutover",
    "--confirm-no-production-session-write",
    "--confirm-no-production-identity-write",
    "--confirm-no-token-persistence",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5r_oauth_identity_production_canary_readiness.md",
    "docs/development/phase_5r_oauth_identity_production_canary_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5r_oauth_identity_production_canary_readiness.py",
    "tools/check_phase5r_oauth_identity_production_canary_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5r_oauth_identity_production_canary_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "deploy/", "nginx/", "systemd/", "migrations/")
FORBIDDEN_EXACT = {"aicrm_next/main.py", "aicrm_next/questionnaire/oauth.py"}
FORBIDDEN_DOC_CLAIMS = {
    "production canary executed",
    "production callback cutover enabled",
    "production session write enabled",
    "production identity write enabled",
    "token persistence enabled",
    "production owner switched",
    "fallback removed",
    "production_compat changed",
    "delete_ready true",
    "delete_ready: true",
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


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


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
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
    return imports, calls


def _runner_blockers() -> list[str]:
    blockers: list[str] = []
    text = RUNNER.read_text(encoding="utf-8")
    imports, calls = _imports_calls(RUNNER)
    for arg in REQUIRED_ARGS | {"--output-json", "--output-md"}:
        if arg not in text:
            blockers.append(f"runner missing required arg: {arg}")
    for env in REQUIRED_ENV:
        if env not in text:
            blockers.append(f"runner missing required env: {env}")
    for token in (
        "not_executed_missing_staging_evidence",
        "not_executed_invalid_staging_evidence",
        "not_executed_missing_confirm_no_production_live_oauth_call",
        "not_executed_missing_confirm_no_production_callback_cutover",
        "not_executed_missing_confirm_no_production_session_write",
        "not_executed_missing_confirm_no_production_identity_write",
        "not_executed_missing_confirm_no_token_persistence",
        "not_executed_secret_or_token_leak_risk",
    ):
        if token not in text:
            blockers.append(f"runner missing blocked status: {token}")
    forbidden_imports = {"requests", "httpx", "aiohttp", "urllib", "oauth_identity_live_adapter", "oauth_identity_live_gateway"}
    found_imports = sorted(forbidden_imports & imports)
    if found_imports:
        blockers.append(f"runner imports forbidden modules: {found_imports}")
    forbidden_calls = {"build_live_oauth_identity_adapter", "exchange_code_live", "set_cookie", "write_session", "write_identity", "persist_token", "send"}
    found_calls = sorted(forbidden_calls & calls)
    if found_calls:
        blockers.append(f"runner calls forbidden live/write names: {found_calls}")
    for token in ("api.weixin.qq.com", "sns/oauth2/access_token", "production_callback_cutover_executed: true"):
        if token in text.lower():
            blockers.append(f"runner contains forbidden live token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, RUNNER, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()
    if data.get("status") != "phase_5r_oauth_identity_production_canary_readiness_no_execution":
        blockers.append("status mismatch")
    if data.get("route_family") != "/api/h5/wechat/oauth*":
        blockers.append("route_family must be /api/h5/wechat/oauth*")
    auth = _dict(data.get("authorizations"))
    for key, value in auth.items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    for key in ("production_canary_execution_authorized", "production_live_oauth_call_authorized", "production_callback_cutover_authorized", "production_session_write_authorized", "production_identity_write_authorized", "token_persistence_authorized", "production_compat_change_authorized", "fallback_removal_authorized"):
        if auth.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")
    runner = _dict(data.get("readiness_runner"))
    if runner.get("default_blocked") is not True:
        blockers.append("readiness_runner.default_blocked must be true")
    for key in ("production_live_oauth_call_executed", "production_callback_cutover_executed", "production_session_write_executed", "production_identity_write_executed", "token_persisted"):
        if runner.get(key) is not False:
            blockers.append(f"readiness_runner.{key} must be false")
    if runner.get("requires_staging_evidence_json") is not True:
        blockers.append("readiness_runner.requires_staging_evidence_json must be true")
    if not REQUIRED_ENV <= _strings(runner.get("required_env")):
        blockers.append("readiness_runner.required_env incomplete")
    if not REQUIRED_ARGS <= _strings(runner.get("required_args")):
        blockers.append("readiness_runner.required_args incomplete")
    req = _dict(data.get("staging_evidence_requirements"))
    for key, value in req.items():
        if key == "blocked_evidence_qualifies":
            if value is not False:
                blockers.append("staging_evidence_requirements.blocked_evidence_qualifies must be false")
        elif value is not True:
            blockers.append(f"staging_evidence_requirements.{key} must be true")
    target = _dict(data.get("production_callback_target_policy"))
    for key in ("single_callback_attempt_only", "raw_code_output_forbidden", "raw_state_output_forbidden", "raw_token_output_forbidden", "raw_secret_output_forbidden"):
        if target.get(key) is not True:
            blockers.append(f"production_callback_target_policy.{key} must be true")
    for key in ("batch_replay_allowed", "production_callback_url_cutover_allowed", "production_session_write_allowed", "production_identity_write_allowed", "token_persistence_allowed", "outbound_send_allowed", "timer_execution_allowed", "automation_execution_allowed"):
        if target.get(key) is not False:
            blockers.append(f"production_callback_target_policy.{key} must be false")
    rollback = _dict(data.get("rollback_policy"))
    for key in ("rollback_owner_required", "cleanup_requires_explicit_approval", "cleanup_evidence_required", "unrelated_session_or_identity_cleanup_forbidden"):
        if rollback.get(key) is not True:
            blockers.append(f"rollback_policy.{key} must be true")
    for key in ("automatic_cleanup_allowed", "batch_cleanup_allowed"):
        if rollback.get(key) is not False:
            blockers.append(f"rollback_policy.{key} must be false")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#730":
        blockers.append("phase_execution_state.last_merged_pr must be #730")
    if state.get("last_attempted_action") != "phase_5r_oauth_identity_production_canary_readiness_bundle":
        blockers.append("last_attempted_action must be Phase 5R")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    blockers.extend(_runner_blockers())
    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc must not claim forbidden state: {claim}")
    changed = _changed_files()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5R allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"forbidden changed files: {forbidden}")
    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5R Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
