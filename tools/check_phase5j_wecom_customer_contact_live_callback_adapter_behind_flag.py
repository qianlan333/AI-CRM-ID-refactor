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


DOC = ROOT / "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py"
PRODUCTION_RUNNER = ROOT / "tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py"
RUNTIME_FILES = [
    ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py",
    ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_live_gateway.py",
    ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
]
ROUTE_FAMILY = "/wecom/external-contact/callback"
CAPABILITY_OWNER = "aicrm_next.integration_gateway"
BUNDLE_TYPE = "phase_5_external_adapter_live_adapter_behind_flag_bundle"
NEXT_BUNDLE = "phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence_bundle"
COMPLETED_STEP = "phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag_completed"
REQUIRED_METHODS = {
    "verify_callback_live",
    "process_external_contact_callback_live",
    "record_contact_event_live",
    "record_identity_mapping_live",
}
REQUIRED_FLAGS = {
    "AICRM_WECOM_CONTACT_CALLBACK_LIVE_ADAPTER_ENABLED",
    "AICRM_WECOM_CONTACT_CALLBACK_LIVE_PROCESSING_APPROVED",
    "AICRM_WECOM_CONTACT_CALLBACK_CONFIG_REVIEWED",
}
REQUIRED_ERROR_CODES = {
    "live_adapter_not_enabled",
    "live_callback_not_approved",
    "callback_config_missing",
    "idempotency_key_required",
    "duplicate_idempotency_key",
    "event_type_unsupported",
    "external_userid_missing",
    "follow_user_userid_missing",
    "wecom_live_callback_failed",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
    "aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py",
    "aicrm_next/integration_gateway/wecom_contact_callback_live_gateway.py",
    "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.md",
    "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py",
    "tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py",
    "tools/check_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {"aicrm_next/main.py"}
FORBIDDEN_CHANGED_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "deploy/", "nginx/", "systemd/", "migrations/")
FORBIDDEN_IMPORT_ROOTS = {"requests", "httpx", "aiohttp", "wecom_ability_service", "wecom_client"}
FORBIDDEN_CALL_NAMES = {"send", "send_message", "payment", "media_upload", "openclaw", "mcp", "run_due"}
FORBIDDEN_DOC_CLAIMS = {
    "production callback cutover enabled",
    "production contact write enabled",
    "production identity mapping write enabled",
    "route owner switched",
    "fallback removed",
    "production_compat changed",
    "canary approved",
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


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
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


def _runtime_static_report() -> list[str]:
    blockers: list[str] = []
    combined = "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME_FILES)
    for flag in REQUIRED_FLAGS:
        if flag not in combined:
            blockers.append(f"live adapter must reference explicit flag {flag}")
    if "idempotency_key" not in combined:
        blockers.append("live adapter must require idempotency_key")
    if "side_effect_safety" not in combined:
        blockers.append("live adapter must expose side_effect_safety")
    for path in RUNTIME_FILES:
        imports, calls = _imports_and_calls(path)
        forbidden_imports = sorted(FORBIDDEN_IMPORT_ROOTS & imports)
        if forbidden_imports:
            blockers.append(f"{path.relative_to(ROOT)} imports forbidden live/network modules: {forbidden_imports}")
        forbidden_calls = sorted(FORBIDDEN_CALL_NAMES & calls)
        if forbidden_calls:
            blockers.append(f"{path.relative_to(ROOT)} contains forbidden call names: {forbidden_calls}")
    return blockers


def _runner_static_report(path: Path, *, required_args: set[str]) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8")
    imports, calls = _imports_and_calls(path)
    forbidden_imports = sorted(FORBIDDEN_IMPORT_ROOTS & imports)
    if forbidden_imports:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden live/network modules: {forbidden_imports}")
    for arg in {"--output-json", "--output-md", *required_args}:
        if arg not in text:
            blockers.append(f"{path.relative_to(ROOT)} must support {arg}")
    forbidden_calls = sorted(FORBIDDEN_CALL_NAMES & calls)
    if forbidden_calls:
        blockers.append(f"{path.relative_to(ROOT)} contains forbidden call names: {forbidden_calls}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    required_paths = [DOC, PLAN_YAML, STAGING_RUNNER, PRODUCTION_RUNNER, STATE, TEST, *RUNTIME_FILES]
    for path in required_paths:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_5j_wecom_customer_contact_live_callback_adapter_behind_explicit_flag":
        blockers.append("status must be phase_5j_wecom_customer_contact_live_callback_adapter_behind_explicit_flag")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")

    auth = _dict(data.get("authorizations"))
    if auth.get("live_callback_adapter_code_authorized") is not True:
        blockers.append("live_callback_adapter_code_authorized must be true")
    for key, value in sorted(auth.items()):
        if key != "live_callback_adapter_code_authorized" and value is not False:
            blockers.append(f"authorizations.{key} must be false")

    live_adapter = _dict(data.get("live_adapter"))
    if live_adapter.get("default_enabled") is not False:
        blockers.append("live_adapter.default_enabled must be false")
    if not REQUIRED_FLAGS <= _strings(live_adapter.get("required_env")):
        blockers.append("live_adapter.required_env missing explicit flags")
    if REQUIRED_METHODS - _strings(live_adapter.get("methods")):
        blockers.append("live_adapter.methods incomplete")

    missing_errors = sorted(REQUIRED_ERROR_CODES - _strings(_dict(data.get("error_mapping")).get("required_error_codes")))
    if missing_errors:
        blockers.append(f"error_mapping missing: {missing_errors}")
    for key, value in sorted(_dict(data.get("side_effect_safety")).items()):
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")
    idem = _dict(data.get("idempotency"))
    for key in ("record_contact_event_live_requires_key", "record_identity_mapping_live_requires_key", "replay_same_hash", "conflict_different_hash", "no_partial_production_side_effect_when_blocked"):
        if idem.get(key) is not True:
            blockers.append(f"idempotency.{key} must be true")

    staging = _dict(data.get("staging_evidence"))
    if staging.get("default_blocked") is not True or staging.get("execute_live_staging_requires_approval") is not True:
        blockers.append("staging_evidence must be default blocked and approval-gated")
    prod = _dict(data.get("production_dry_run_gate"))
    if prod.get("live_callback_processed") is not False:
        blockers.append("production_dry_run_gate.live_callback_processed must be false")
    if prod.get("production_contact_write_executed") is not False or prod.get("production_identity_mapping_write_executed") is not False:
        blockers.append("production dry-run gate production writes must be false")

    business = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "legacy_fallback_retained", "production_compat_unchanged"):
        if business.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle.recommended_next_step must be {NEXT_BUNDLE}")

    if state.get("last_merged_pr") != "#722":
        blockers.append("phase_execution_state.last_merged_pr must be #722")
    if state.get("last_attempted_action") != "phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag_bundle":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 5J")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"phase_execution_state.next_allowed_actions must be exactly {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"completed_steps missing {COMPLETED_STEP}")

    blockers.extend(_runtime_static_report())
    blockers.extend(_runner_static_report(STAGING_RUNNER, required_args={"--dry-run-live-gate", "--execute-live-staging", "--confirm-live-wecom-callback"}))
    blockers.extend(_runner_static_report(PRODUCTION_RUNNER, required_args={"--dry-run", "--confirm-no-live-callback"}))

    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc must not claim forbidden state: {claim}")

    changed_files, change_warnings = _changed_files()
    warnings.extend(change_warnings)
    details["changed_files"] = sorted(changed_files)
    unexpected = sorted(path for path in changed_files if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5J allowlist: {unexpected}")
    for path in sorted(changed_files):
        if path in FORBIDDEN_EXACT_CHANGED or any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES):
            blockers.append(f"forbidden changed file for Phase 5J: {path}")

    ok = not blockers
    return {"overall": "PASS" if ok else "FAIL", "ok": ok, "autopilot_deliverable": ok, "blockers": blockers, "warnings": warnings, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 5J WeCom Contact Live Callback Adapter Check", "", f"- overall: {report.get('overall')}", f"- ok: {str(report.get('ok')).lower()}", "", "## Blockers"]
    lines.extend([f"- {item}" for item in report.get("blockers", [])] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in report.get("warnings", [])] or ["- none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 5J WeCom customer contact live callback adapter behind explicit flag.")
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
