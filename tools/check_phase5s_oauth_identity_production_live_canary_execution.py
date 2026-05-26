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


DOC = ROOT / "docs/development/phase_5s_oauth_identity_production_live_canary_execution.md"
PLAN_YAML = ROOT / "docs/development/phase_5s_oauth_identity_production_live_canary_execution.yaml"
CANARY_RUNNER = ROOT / "tools/run_phase5s_oauth_identity_production_live_canary_execution.py"
CLEANUP_RUNNER = ROOT / "tools/run_phase5s_oauth_identity_production_canary_cleanup.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5s_oauth_identity_production_live_canary_execution.py"
NEXT_BUNDLE = "phase_5t_oauth_identity_family_acceptance_bundle"
COMPLETED_STEP = "phase_5s_oauth_identity_production_live_canary_execution_completed"
REQUIRED_ENV = {
    "AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED",
    "AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED",
    "AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED",
    "AICRM_PHASE5S_OAUTH_IDENTITY_PRODUCTION_CANARY_APPROVED",
    "AICRM_PHASE5S_OAUTH_IDENTITY_CALLBACK_TARGET_APPROVED",
    "AICRM_PHASE5S_OAUTH_IDENTITY_ROLLBACK_OWNER_APPROVED",
    "AICRM_PHASE5S_OAUTH_IDENTITY_CLEANUP_STRATEGY_APPROVED",
}
REQUIRED_ARGS = {
    "--phase5r-readiness-json",
    "--staging-evidence-json",
    "--state",
    "--code",
    "--idempotency-key",
    "--confirm-production-live-oauth-call",
    "--confirm-single-approved-callback",
    "--confirm-no-production-callback-cutover",
    "--confirm-no-production-session-write",
    "--confirm-no-production-identity-write",
    "--confirm-no-token-persistence",
    "--confirm-rollback-owner-approved",
    "--confirm-no-batch-replay",
}
CLEANUP_REQUIRED_ARGS = {
    "--canary-evidence-json",
    "--confirm-production-cleanup-reviewed",
    "--confirm-no-production-session-delete",
    "--confirm-no-production-identity-delete",
    "--confirm-rollback-owner-approved",
    "--confirm-no-batch-cleanup",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5s_oauth_identity_production_live_canary_execution.md",
    "docs/development/phase_5s_oauth_identity_production_live_canary_execution.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5s_oauth_identity_production_live_canary_execution.py",
    "tools/run_phase5s_oauth_identity_production_canary_cleanup.py",
    "tools/check_phase5s_oauth_identity_production_live_canary_execution.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5s_oauth_identity_production_live_canary_execution.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "deploy/", "nginx/", "systemd/", "migrations/")
FORBIDDEN_EXACT = {"aicrm_next/main.py", "aicrm_next/questionnaire/oauth.py"}
FORBIDDEN_DOC_CLAIMS = {
    "route owner switched",
    "fallback removed",
    "production session write enabled",
    "production identity write enabled",
    "token persistence enabled",
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
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
    return imports, calls


def _runner_blockers() -> list[str]:
    blockers: list[str] = []
    canary_text = CANARY_RUNNER.read_text(encoding="utf-8")
    cleanup_text = CLEANUP_RUNNER.read_text(encoding="utf-8")
    canary_imports, canary_calls = _imports_calls(CANARY_RUNNER)
    cleanup_imports, cleanup_calls = _imports_calls(CLEANUP_RUNNER)
    for arg in REQUIRED_ARGS | {"--safe-test-code", "--output-json", "--output-md"}:
        if arg not in canary_text:
            blockers.append(f"canary runner missing required arg: {arg}")
    for arg in CLEANUP_REQUIRED_ARGS | {"--output-json", "--output-md"}:
        if arg not in cleanup_text:
            blockers.append(f"cleanup runner missing required arg: {arg}")
    for env in REQUIRED_ENV:
        if env not in canary_text:
            blockers.append(f"canary runner missing required env: {env}")
    for token in (
        "not_executed_missing_phase5r_readiness",
        "not_executed_invalid_phase5r_readiness",
        "not_executed_missing_staging_evidence",
        "not_executed_invalid_staging_evidence",
        "not_executed_missing_canary_approval",
        "not_executed_missing_callback_target_approval",
        "not_executed_missing_rollback_owner",
        "not_executed_missing_cleanup_strategy",
        "not_executed_missing_state",
        "not_executed_missing_code",
        "not_executed_missing_idempotency_key",
        "not_executed_missing_confirm_production_live_oauth_call",
        "not_executed_missing_confirm_single_callback",
        "not_executed_missing_confirm_no_callback_cutover",
        "not_executed_missing_confirm_no_session_write",
        "not_executed_missing_confirm_no_identity_write",
        "not_executed_missing_confirm_no_token_persistence",
        "not_executed_missing_confirm_no_batch_replay",
        "not_executed_secret_or_token_leak_risk",
    ):
        if token not in canary_text:
            blockers.append(f"canary runner missing blocked status: {token}")
    forbidden_import_roots = {"requests", "httpx", "aiohttp", "urllib", "aicrm_next.integration_gateway.oauth_identity_live_gateway"}
    found_canary_imports = sorted(forbidden_import_roots & canary_imports)
    found_cleanup_imports = sorted(forbidden_import_roots & cleanup_imports)
    if found_canary_imports:
        blockers.append(f"canary runner imports forbidden modules: {found_canary_imports}")
    if found_cleanup_imports:
        blockers.append(f"cleanup runner imports forbidden modules: {found_cleanup_imports}")
    forbidden_calls = {
        "set_cookie",
        "write_session",
        "write_identity",
        "persist_token",
        "delete_session",
        "delete_identity",
        "revoke_token",
        "send",
        "post",
        "put",
        "patch",
        "delete",
    }
    canary_bad_calls = sorted(forbidden_calls & canary_calls)
    cleanup_bad_calls = sorted(forbidden_calls & cleanup_calls)
    if canary_bad_calls:
        blockers.append(f"canary runner calls forbidden names: {canary_bad_calls}")
    if cleanup_bad_calls:
        blockers.append(f"cleanup runner calls forbidden names: {cleanup_bad_calls}")
    for token in (
        "batch replay allowed",
        "production_compat",
        "route_owner_switch",
        "production_session_write_executed: true",
        "production_identity_write_executed: true",
        "token_persisted: true",
        "outbound_send",
        "payment",
        "media_upload",
        "wecom",
        "openclaw",
        "mcp",
    ):
        if token in canary_text.lower() and token in {"production_session_write_executed: true", "production_identity_write_executed: true", "token_persisted: true", "route_owner_switch"}:
            blockers.append(f"canary runner contains forbidden token: {token}")
    if "build_live_oauth_identity_application_service" not in canary_text or "confirm_live_oauth_callback=True" not in canary_text:
        blockers.append("canary runner must use existing Phase 5P application boundary behind explicit confirm")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    for path in (DOC, PLAN_YAML, CANARY_RUNNER, CLEANUP_RUNNER, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers}
    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()
    if data.get("status") != "phase_5s_oauth_identity_production_live_canary_execution_bundle":
        blockers.append("status mismatch")
    if data.get("bundle_type") != "phase_5_external_adapter_production_live_canary_execution_bundle":
        blockers.append("bundle_type mismatch")
    if data.get("route_family") != "/api/h5/wechat/oauth*":
        blockers.append("route_family must be /api/h5/wechat/oauth*")
    if data.get("capability_owner") != "aicrm_next.integration_gateway":
        blockers.append("capability_owner must be aicrm_next.integration_gateway")
    auth = _dict(data.get("authorizations"))
    if auth.get("production_live_canary_tooling_authorized") is not True:
        blockers.append("authorizations.production_live_canary_tooling_authorized must be true")
    for key in (
        "production_live_oauth_call_by_default_authorized",
        "production_callback_cutover_authorized",
        "production_session_write_authorized",
        "production_identity_write_authorized",
        "token_persistence_authorized",
        "production_owner_switch_authorized",
        "production_compat_change_authorized",
        "fallback_removal_authorized",
    ):
        if auth.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")
    canary = _dict(data.get("production_canary"))
    for key in ("default_blocked", "single_callback_attempt_only", "requires_phase5r_readiness_json", "requires_staging_evidence_json"):
        if canary.get(key) is not True:
            blockers.append(f"production_canary.{key} must be true")
    for key in ("batch_replay_allowed", "production_callback_cutover_allowed", "production_session_write_allowed", "production_identity_write_allowed", "token_persistence_allowed"):
        if canary.get(key) is not False:
            blockers.append(f"production_canary.{key} must be false")
    if not REQUIRED_ENV <= _strings(canary.get("required_env")):
        blockers.append("production_canary.required_env incomplete")
    if not REQUIRED_ARGS <= _strings(canary.get("required_args")):
        blockers.append("production_canary.required_args incomplete")
    cleanup = _dict(data.get("cleanup"))
    if cleanup.get("default_blocked") is not True:
        blockers.append("cleanup.default_blocked must be true")
    for key in ("production_session_delete_allowed", "production_identity_delete_allowed", "token_revocation_allowed_by_default", "batch_cleanup_allowed", "automatic_cleanup_allowed"):
        if cleanup.get(key) is not False:
            blockers.append(f"cleanup.{key} must be false")
    for key in ("cleanup_requires_explicit_approval", "cleanup_evidence_required"):
        if cleanup.get(key) is not True:
            blockers.append(f"cleanup.{key} must be true")
    for key, value in _dict(data.get("side_effect_safety")).items():
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#731":
        blockers.append("phase_execution_state.last_merged_pr must be #731")
    if state.get("last_attempted_action") != "phase_5s_oauth_identity_production_live_canary_execution_bundle":
        blockers.append("last_attempted_action must be Phase 5S")
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
        blockers.append(f"changed files outside Phase 5S allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"forbidden changed files: {forbidden}")
    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5S Check\n\n" + "\n".join(f"- {item}" for item in report.get("blockers", []) or ["none"]) + "\n", encoding="utf-8")


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
