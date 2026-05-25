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


DOC = ROOT / "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.md"
PLAN_YAML = ROOT / "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py"
PRODUCTION_RUNNER = ROOT / "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py"
CHECKER = ROOT / "tools/check_phase5i_wecom_customer_contact_fake_stub_adapter.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5i_wecom_customer_contact_fake_stub_adapter.py"
RUNTIME_FILES = [
    ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_adapter.py",
    ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_contract.py",
    ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
]
ROUTE_FAMILY = "/wecom/external-contact/callback"
CAPABILITY_OWNER = "aicrm_next.integration_gateway"
BUNDLE_TYPE = "phase_5_external_adapter_fake_stub_runtime_and_readiness_bundle"
NEXT_BUNDLE = "phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag_bundle"
COMPLETED_STEP = "phase_5i_wecom_customer_contact_fake_stub_adapter_completed"
REQUIRED_METHODS = {
    "verify_callback_contract",
    "parse_external_contact_event",
    "normalize_external_contact_event",
    "dry_run_record_contact_event",
    "dry_run_identity_mapping",
}
REQUIRED_ERROR_CODES = {
    "callback_config_missing",
    "signature_invalid",
    "decrypt_not_enabled",
    "event_type_unsupported",
    "external_userid_missing",
    "follow_user_userid_missing",
    "idempotency_key_required",
    "duplicate_event_key",
    "live_callback_not_enabled",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
}
REQUIRED_IDEMPOTENCY_TRUE = {
    "event_key_required",
    "dry_run_record_contact_event_requires_key",
    "dry_run_identity_mapping_requires_key",
    "replay_same_event_key",
    "replay_same_hash",
    "conflict_different_hash",
    "no_partial_production_side_effect",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/integration_gateway/wecom_contact_callback_adapter.py",
    "aicrm_next/integration_gateway/wecom_contact_callback_contract.py",
    "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
    "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.md",
    "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py",
    "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py",
    "tools/check_phase5i_wecom_customer_contact_fake_stub_adapter.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5i_wecom_customer_contact_fake_stub_adapter.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {"aicrm_next/main.py"}
FORBIDDEN_CHANGED_PREFIXES = (
    "aicrm_next/production_compat/",
    "wecom_ability_service/",
    "deploy/",
    "nginx/",
    "systemd/",
    "migrations/",
)
FORBIDDEN_IMPORT_ROOTS = {"requests", "httpx", "aiohttp", "wecom_ability_service", "wecom_client"}
FORBIDDEN_RUNTIME_ENV_TOKENS = {
    "WECOM_SECRET",
    "WECHAT_WORK_SECRET",
    "WECOM_CORP_SECRET",
    "CORPSECRET",
    "WECOM_CORP_ID",
    "WECHAT_WORK_CORP_ID",
    "CORPID",
    "AESKEY",
    "AES_KEY",
    "ENCODING_AES_KEY",
}
FORBIDDEN_LIVE_TEXT = {
    "externalcontact/mark_tag",
    "/cgi-bin/externalcontact/mark_tag",
    "get_corp_tag_list",
    "production_callback_owner_switch",
    "send_message",
}
FORBIDDEN_DOC_CLAIMS = {
    "live callback cutover enabled",
    "production contact write enabled",
    "production identity mapping write enabled",
    "production success",
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
    for path in RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        imports, calls = _imports_and_calls(path)
        forbidden_imports = sorted(FORBIDDEN_IMPORT_ROOTS & imports)
        if forbidden_imports:
            blockers.append(f"{path.relative_to(ROOT)} imports forbidden live/network modules: {forbidden_imports}")
        if "os" in imports:
            blockers.append(f"{path.relative_to(ROOT)} must not import os or read environment")
        forbidden_calls = sorted({"mark_tag", "unmark_tag", "send", "send_message", "post", "put", "patch", "delete"} & calls)
        if forbidden_calls:
            blockers.append(f"{path.relative_to(ROOT)} contains forbidden live/network call names: {forbidden_calls}")
        for token in FORBIDDEN_RUNTIME_ENV_TOKENS:
            if token in text:
                blockers.append(f"{path.relative_to(ROOT)} must not read WeCom secret/CorpID/AESKey token: {token}")
        lowered = text.lower()
        for token in FORBIDDEN_LIVE_TEXT:
            if token.lower() in lowered:
                blockers.append(f"{path.relative_to(ROOT)} must not reference forbidden live token: {token}")
    return blockers


def _runner_static_report(path: Path, *, require_args: set[str] | None = None) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8")
    imports, calls = _imports_and_calls(path)
    forbidden_imports = sorted(FORBIDDEN_IMPORT_ROOTS & imports)
    if forbidden_imports:
        blockers.append(f"{path.relative_to(ROOT)} imports forbidden live/network modules: {forbidden_imports}")
    for arg in ("--output-json", "--output-md"):
        if arg not in text:
            blockers.append(f"{path.relative_to(ROOT)} must support {arg}")
    for arg in sorted(require_args or set()):
        if arg not in text:
            blockers.append(f"{path.relative_to(ROOT)} must require/support {arg}")
    forbidden_calls = sorted({"mark_tag", "unmark_tag", "send", "send_message", "post", "put", "patch", "delete"} & calls)
    if forbidden_calls:
        blockers.append(f"{path.relative_to(ROOT)} contains forbidden live/network call names: {forbidden_calls}")
    lowered = text.lower()
    for token in ("externalcontact/mark_tag", "production_callback_owner_switch"):
        if token in lowered:
            blockers.append(f"{path.relative_to(ROOT)} must not reference forbidden live token: {token}")
    for token in FORBIDDEN_RUNTIME_ENV_TOKENS:
        if token in text:
            blockers.append(f"{path.relative_to(ROOT)} must not read WeCom secret/CorpID/AESKey token: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    required_paths = [DOC, PLAN_YAML, STAGING_RUNNER, PRODUCTION_RUNNER, CHECKER, STATE, TEST, *RUNTIME_FILES]
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
    if data.get("status") != "phase_5i_wecom_customer_contact_fake_stub_adapter_no_live_callback":
        blockers.append("status must be phase_5i_wecom_customer_contact_fake_stub_adapter_no_live_callback")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")

    authorizations = _dict(data.get("authorizations"))
    if not authorizations:
        blockers.append("authorizations must be present")
    for key, value in sorted(authorizations.items()):
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    methods = _strings(data.get("implemented_fake_stub_methods"))
    missing_methods = sorted(REQUIRED_METHODS - methods)
    if missing_methods:
        blockers.append(f"implemented_fake_stub_methods missing: {missing_methods}")

    fake_stub = _dict(data.get("fake_stub_runtime"))
    for key in ("live_callback_allowed", "network_call_allowed", "token_usage_allowed", "aes_key_usage_allowed", "db_write_allowed", "production_success_claim_allowed"):
        if fake_stub.get(key) is not False:
            blockers.append(f"fake_stub_runtime.{key} must be false")
    for key in ("deterministic_events_required",):
        if fake_stub.get(key) is not True:
            blockers.append(f"fake_stub_runtime.{key} must be true")

    side_effect_safety = _dict(data.get("side_effect_safety"))
    if not side_effect_safety:
        blockers.append("side_effect_safety must be present")
    for key, value in sorted(side_effect_safety.items()):
        if value is not False:
            blockers.append(f"side_effect_safety.{key} must be false")

    missing_errors = sorted(REQUIRED_ERROR_CODES - _strings(_dict(data.get("error_mapping")).get("required_error_codes")))
    if missing_errors:
        blockers.append(f"error_mapping missing codes: {missing_errors}")

    idempotency = _dict(data.get("idempotency"))
    for key in sorted(REQUIRED_IDEMPOTENCY_TRUE):
        if idempotency.get(key) is not True:
            blockers.append(f"idempotency.{key} must be true")

    runners = _dict(data.get("readiness_runners"))
    staging = _dict(runners.get("staging"))
    production = _dict(runners.get("production_dry_run"))
    if staging.get("path") != "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py":
        blockers.append("readiness_runners.staging.path mismatch")
    if staging.get("default_blocked") is not True or staging.get("live_callback_allowed") is not False:
        blockers.append("staging runner must be default_blocked true and live_callback_allowed false")
    if "AICRM_PHASE5I_WECOM_CONTACT_STAGING_SMOKE_APPROVED" not in _strings(staging.get("required_env")):
        blockers.append("staging runner required_env missing approval")
    if production.get("path") != "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py":
        blockers.append("readiness_runners.production_dry_run.path mismatch")
    if production.get("default_blocked") is not True or production.get("live_callback_allowed") is not False:
        blockers.append("production dry-run runner must be default_blocked true and live_callback_allowed false")
    expected_prod_env = {
        "AICRM_PHASE5I_WECOM_CONTACT_PRODUCTION_DRY_RUN_APPROVED",
        "AICRM_PHASE5I_WECOM_CONTACT_PRODUCTION_CONFIG_REVIEWED",
    }
    if not expected_prod_env <= _strings(production.get("required_env")):
        blockers.append("production dry-run runner required_env incomplete")
    if {"--dry-run", "--confirm-no-live-callback"} - _strings(production.get("required_args")):
        blockers.append("production dry-run runner required_args incomplete")

    business = _dict(data.get("business_continuity"))
    for key in ("production_behavior_unchanged", "legacy_fallback_retained", "no_external_side_effect_enabled", "fake_stub_only"):
        if business.get(key) is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _dict(data.get("next_bundle")).get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle.recommended_next_step must be {NEXT_BUNDLE}")

    state_next = set(_list(state.get("next_allowed_actions")))
    if state.get("last_merged_pr") != "#720":
        blockers.append("phase_execution_state.last_merged_pr must be #720")
    if state.get("last_attempted_action") != "phase_5i_wecom_customer_contact_fake_stub_adapter_bundle":
        blockers.append("phase_execution_state.last_attempted_action must be phase_5i_wecom_customer_contact_fake_stub_adapter_bundle")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if state_next != {NEXT_BUNDLE}:
        blockers.append(f"phase_execution_state.next_allowed_actions must be exactly {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"phase_execution_state.completed_steps missing {COMPLETED_STEP}")

    blockers.extend(_runtime_static_report())
    blockers.extend(_runner_static_report(STAGING_RUNNER))
    blockers.extend(_runner_static_report(PRODUCTION_RUNNER, require_args={"--dry-run", "--confirm-no-live-callback"}))

    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc must not claim forbidden state: {claim}")

    changed_files, change_warnings = _changed_files()
    warnings.extend(change_warnings)
    details["changed_files"] = sorted(changed_files)
    unexpected = sorted(path for path in changed_files if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5I allowlist: {unexpected}")
    for path in sorted(changed_files):
        if path in FORBIDDEN_EXACT_CHANGED or any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES):
            blockers.append(f"forbidden changed file for Phase 5I: {path}")

    details.update(
        {
            "route_family": data.get("route_family"),
            "capability_owner": data.get("capability_owner"),
            "implemented_methods": sorted(methods),
            "next_bundle": _dict(data.get("next_bundle")).get("recommended_next_step"),
        }
    )
    ok = not blockers
    return {
        "overall": "PASS" if ok else "FAIL",
        "ok": ok,
        "autopilot_deliverable": ok,
        "blockers": blockers,
        "warnings": warnings,
        "details": details,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5I WeCom Customer Contact Fake/Stub Adapter Check",
        "",
        f"- overall: {report.get('overall')}",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- autopilot_deliverable: {str(report.get('autopilot_deliverable')).lower()}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers", [])
    lines.extend([f"- {item}" for item in blockers] or ["- none"])
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings", [])
    lines.extend([f"- {item}" for item in warnings] or ["- none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 5I WeCom customer contact fake/stub adapter bundle.")
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
