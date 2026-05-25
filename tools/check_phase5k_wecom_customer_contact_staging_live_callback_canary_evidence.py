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


DOC = ROOT / "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py"
PRODUCTION_REVIEW_RUNNER = ROOT / "tools/run_phase5k_wecom_customer_contact_production_callback_readiness_review.py"
TEST = ROOT / "tests/test_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py"
ROUTE_FAMILY = "/wecom/external-contact/callback"
NEXT_BUNDLE = "phase_5l_wecom_customer_contact_production_callback_canary_readiness_bundle"
COMPLETED_STEP = "phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence_completed"
REQUIRED_ENV = {
    "AICRM_WECOM_CONTACT_CALLBACK_LIVE_ADAPTER_ENABLED",
    "AICRM_WECOM_CONTACT_CALLBACK_LIVE_PROCESSING_APPROVED",
    "AICRM_WECOM_CONTACT_CALLBACK_CONFIG_REVIEWED",
    "AICRM_PHASE5K_WECOM_CONTACT_STAGING_CANARY_APPROVED",
    "AICRM_PHASE5K_WECOM_CONTACT_STAGING_CANARY_TARGET_APPROVED",
}
REQUIRED_ARGS = {
    "--execute-staging-canary",
    "--confirm-live-wecom-callback",
    "--confirm-staging-only",
    "--confirm-approved-event",
    "--idempotency-key",
    "--external-userid",
    "--event-key",
}
REQUIRED_BLOCKED_STATUSES = {
    "not_executed_missing_live_adapter_enabled",
    "not_executed_missing_live_callback_approval",
    "not_executed_missing_config_review",
    "not_executed_missing_staging_canary_approval",
    "not_executed_missing_target_approval",
    "not_executed_missing_external_userid",
    "not_executed_missing_event_key",
    "not_executed_missing_idempotency_key",
    "not_executed_missing_confirm_live_callback",
    "not_executed_missing_confirm_staging_only",
    "not_executed_missing_confirm_approved_event",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.md",
    "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
    "tools/run_phase5k_wecom_customer_contact_production_callback_readiness_review.py",
    "tools/check_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {"aicrm_next/main.py"}
FORBIDDEN_CHANGED_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "deploy/", "nginx/", "systemd/", "migrations/")
FORBIDDEN_DOC_CLAIMS = {
    "production callback cutover enabled",
    "production contact write enabled",
    "production identity mapping write enabled",
    "production canary approved",
    "fallback removed",
    "production_compat changed",
    "delete_ready true",
    "delete_ready: true",
}


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, stderr = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    else:
        warnings.append(f"git ls-files --others unavailable: {(stderr or stdout).strip()}")
    return changed, warnings


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


def _call_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _runner_blockers() -> list[str]:
    blockers: list[str] = []
    text = STAGING_RUNNER.read_text(encoding="utf-8")
    for arg in {"--output-json", "--output-md"} | REQUIRED_ARGS:
        if arg not in text:
            blockers.append(f"staging runner missing required arg: {arg}")
    for env in REQUIRED_ENV | {"AICRM_WECOM_CONTACT_CALLBACK_CORP_ID", "AICRM_WECOM_CONTACT_CALLBACK_TOKEN", "AICRM_WECOM_CONTACT_CALLBACK_AES_KEY"}:
        if env not in text:
            blockers.append(f"staging runner missing env gate: {env}")
    for status in REQUIRED_BLOCKED_STATUSES:
        if status not in text:
            blockers.append(f"staging runner missing blocked status: {status}")
    for token in ("not_executed_batch_target_rejected", "not_executed_batch_event_rejected", "_redact_external_userid", "phase5j_staging.build_report", "cleanup_rollback_guidance"):
        if token not in text:
            blockers.append(f"staging runner missing safety token: {token}")
    forbidden_calls = sorted({"send", "send_message", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(STAGING_RUNNER))
    if forbidden_calls:
        blockers.append(f"staging runner contains forbidden side-effect calls: {forbidden_calls}")
    review_text = PRODUCTION_REVIEW_RUNNER.read_text(encoding="utf-8")
    for arg in ("--staging-evidence-json", "--confirm-no-production-live-callback", "--output-json", "--output-md"):
        if arg not in review_text:
            blockers.append(f"production review runner missing arg: {arg}")
    for token in ("production_live_callback_processed", "production_contact_write_executed", "production_identity_mapping_write_executed", "route_owner_changed", "production_compat_changed", "fallback_removed"):
        if token not in review_text:
            blockers.append(f"production review runner missing output field: {token}")
    forbidden_review_tokens = {"build_live_wecom_contact_callback_adapter", "process_external_contact_callback_live", "wecom_ability_service", "requests", "httpx", "aiohttp"}
    found = sorted(token for token in forbidden_review_tokens if token in review_text)
    if found:
        blockers.append(f"production review must never call live callback: {found}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, STAGING_RUNNER, PRODUCTION_REVIEW_RUNNER, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("status") != "phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence":
        blockers.append("status mismatch")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    auth = _dict(data.get("authorizations"))
    if auth.get("staging_live_callback_canary_possible_with_approval") is not True:
        blockers.append("staging canary possible authorization must be true")
    for key, value in sorted(auth.items()):
        if key != "staging_live_callback_canary_possible_with_approval" and value is not False:
            blockers.append(f"authorizations.{key} must be false")
    staging = _dict(data.get("staging_canary"))
    if staging.get("default_blocked") is not True:
        blockers.append("staging_canary.default_blocked must be true")
    if not REQUIRED_ENV <= _strings(staging.get("required_env")):
        blockers.append("staging_canary.required_env incomplete")
    if not REQUIRED_ARGS <= _strings(staging.get("required_args")):
        blockers.append("staging_canary.required_args incomplete")
    target = _dict(data.get("target_safety"))
    for key in ("single_external_userid_only", "single_event_only", "target_approval_required", "external_userid_redaction_required", "raw_token_output_forbidden", "raw_secret_output_forbidden", "raw_aes_key_output_forbidden"):
        if target.get(key) is not True:
            blockers.append(f"target_safety.{key} must be true")
    for key in ("batch_targets_allowed", "batch_events_allowed"):
        if target.get(key) is not False:
            blockers.append(f"target_safety.{key} must be false")
    for key, value in sorted(_dict(data.get("side_effect_safety")).items()):
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    review = _dict(data.get("production_readiness_review"))
    if review.get("production_live_callback_processed") is not False:
        blockers.append("production_readiness_review.production_live_callback_processed must be false")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next bundle must be {NEXT_BUNDLE}")
    if state.get("last_merged_pr") != "#723":
        blockers.append("phase_execution_state.last_merged_pr must be #723")
    if state.get("last_attempted_action") != "phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence_bundle":
        blockers.append("last_attempted_action must be Phase 5K")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")
    blockers.extend(_runner_blockers())
    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc must not claim forbidden state: {claim}")
    changed_files, change_warnings = _changed_files()
    warnings.extend(change_warnings)
    details["changed_files"] = sorted(changed_files)
    unexpected = sorted(path for path in changed_files if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5K allowlist: {unexpected}")
    for path in sorted(changed_files):
        if path in FORBIDDEN_EXACT_CHANGED or any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES):
            blockers.append(f"forbidden changed file for Phase 5K: {path}")
    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers, "warnings": warnings, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 5K WeCom Contact Staging Live Callback Canary Check", "", f"- overall: {report.get('overall')}", f"- ok: {str(report.get('ok')).lower()}", "", "## Blockers"]
    lines.extend([f"- {item}" for item in report.get("blockers", [])] or ["- none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 5K WeCom contact staging live callback canary evidence bundle.")
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
