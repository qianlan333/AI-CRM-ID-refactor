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


DOC = ROOT / "docs/development/phase_5n_oauth_identity_adapter_contract.md"
PLAN_YAML = ROOT / "docs/development/phase_5n_oauth_identity_adapter_contract.yaml"
RUNNER = ROOT / "tools/run_phase5n_oauth_identity_adapter_contract_evidence.py"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase5n_oauth_identity_adapter_contract.py"
ROUTE_FAMILY = "/api/h5/wechat/oauth*"
CAPABILITY_OWNER = "aicrm_next.integration_gateway"
BUNDLE_TYPE = "phase_5_external_adapter_contract_bundle"
NEXT_BUNDLE = "phase_5o_oauth_identity_fake_stub_adapter_bundle"
COMPLETED_STEP = "phase_5n_oauth_identity_adapter_contract_completed"
REQUIRED_METHODS = {
    "build_oauth_authorize_url_contract",
    "parse_oauth_callback_contract",
    "normalize_oauth_identity_event",
    "dry_run_record_oauth_identity",
    "dry_run_session_identity_evidence",
}
REQUIRED_ERROR_CODES = {
    "oauth_config_missing",
    "oauth_code_missing",
    "state_missing",
    "state_invalid",
    "redirect_uri_invalid",
    "openid_missing",
    "idempotency_key_required",
    "duplicate_oauth_event_key",
    "live_oauth_callback_not_enabled",
    "token_exchange_not_enabled",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
}
REQUIRED_IDEMPOTENCY_TRUE = {
    "oauth_event_key_required",
    "idempotency_key_required_for_write_like_dry_run",
    "replay_same_oauth_event_key",
    "conflict_different_hash",
    "no_partial_production_side_effect",
}
REQUIRED_EVIDENCE_TRUE = {
    "live_oauth_call_executed_field_required",
    "live_callback_processed_field_required",
    "production_session_write_executed_field_required",
    "production_identity_write_executed_field_required",
    "side_effect_safety_required",
    "operator_required",
    "request_hash_required",
    "openid_redaction_required",
    "unionid_redaction_required",
    "timestamp_required",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_5n_oauth_identity_adapter_contract.md",
    "docs/development/phase_5n_oauth_identity_adapter_contract.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5n_oauth_identity_adapter_contract_evidence.py",
    "tools/check_phase5n_oauth_identity_adapter_contract.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5n_oauth_identity_adapter_contract.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT_CHANGED = {
    "aicrm_next/main.py",
    "aicrm_next/questionnaire/oauth.py",
}
FORBIDDEN_CHANGED_PREFIXES = (
    "aicrm_next/production_compat/",
    "wecom_ability_service/",
    "deploy/",
    "nginx/",
    "systemd/",
    "migrations/",
)
FORBIDDEN_RUNNER_IMPORTS = {
    "requests",
    "httpx",
    "aiohttp",
    "wecom_ability_service",
    "wechat_oauth",
    "urllib",
}
FORBIDDEN_RUNNER_ENV_TOKENS = {
    "WECHAT_APP_SECRET",
    "WECHAT_SECRET",
    "WECHAT_APPID",
    "WECHAT_APP_ID",
    "WECHAT_ACCESS_TOKEN",
    "WECHAT_REFRESH_TOKEN",
    "OAUTH_CLIENT_SECRET",
    "OAUTH_CLIENT_ID",
}
FORBIDDEN_RUNNER_TEXT = {
    "sns/oauth2/access_token",
    "api.weixin.qq.com",
    "exchange_code",
    "session[",
    "set_cookie",
    "send_message",
}
FORBIDDEN_DOC_CLAIMS = {
    "live oauth callback cutover enabled",
    "production session write enabled",
    "production identity write enabled",
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


def _runner_static_report() -> list[str]:
    blockers: list[str] = []
    text = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports: set[str] = set()
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                call_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                call_names.add(func.attr)

    forbidden_imports = sorted(FORBIDDEN_RUNNER_IMPORTS & imports)
    if forbidden_imports:
        blockers.append(f"runner imports forbidden live/network modules: {forbidden_imports}")
    if "os" in imports:
        blockers.append("runner must not import os or read environment")
    for arg in ("--output-json", "--output-md"):
        if arg not in text:
            blockers.append(f"runner must support {arg}")
    if "--mode" not in text or "fake_stub_contract" not in text:
        blockers.append("runner must support --mode fake_stub_contract")
    forbidden_calls = sorted({"post", "put", "patch", "delete", "send", "set_cookie"} & call_names)
    if forbidden_calls:
        blockers.append(f"runner contains forbidden live/network/session call names: {forbidden_calls}")
    lowered = text.lower()
    for token in FORBIDDEN_RUNNER_TEXT:
        if token.lower() in lowered:
            blockers.append(f"runner must not reference forbidden OAuth/session token: {token}")
    for token in FORBIDDEN_RUNNER_ENV_TOKENS:
        if token in text:
            blockers.append(f"runner must not read OAuth secret/AppID/token env: {token}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, PLAN_YAML, RUNNER, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_5n_oauth_identity_adapter_contract_no_live_oauth_callback":
        blockers.append("status must be phase_5n_oauth_identity_adapter_contract_no_live_oauth_callback")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")
    if data.get("integration_boundary") != CAPABILITY_OWNER:
        blockers.append(f"integration_boundary must be {CAPABILITY_OWNER}")

    authorizations = _dict(data.get("authorizations"))
    if not authorizations:
        blockers.append("authorizations must be present")
    for key, value in sorted(authorizations.items()):
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    methods = _list(_dict(data.get("adapter_contract")).get("methods"))
    method_names = {str(item.get("name")) for item in methods if isinstance(item, dict)}
    missing_methods = sorted(REQUIRED_METHODS - method_names)
    if missing_methods:
        blockers.append(f"adapter_contract.methods missing: {missing_methods}")
    for method in methods:
        item = _dict(method)
        if item.get("live_oauth_call_allowed") is not False:
            blockers.append(f"method {item.get('name')} must set live_oauth_call_allowed false")
        if str(item.get("name", "")).startswith("dry_run_") and item.get("idempotency_required") is not True:
            blockers.append(f"method {item.get('name')} must require idempotency")

    fake_stub = _dict(data.get("fake_stub_contract"))
    for key in ("network_call_allowed", "token_usage_allowed", "code_exchange_allowed", "session_write_allowed", "db_write_allowed", "production_success_claim_allowed"):
        if fake_stub.get(key) is not False:
            blockers.append(f"fake_stub_contract {key} must be false")
    if fake_stub.get("deterministic_oauth_events_required") is not True:
        blockers.append("fake_stub_contract deterministic_oauth_events_required must be true")

    missing_errors = sorted(REQUIRED_ERROR_CODES - _strings(_dict(data.get("error_mapping")).get("required_error_codes")))
    if missing_errors:
        blockers.append(f"error_mapping missing codes: {missing_errors}")

    idempotency = _dict(data.get("idempotency_policy"))
    for key in sorted(REQUIRED_IDEMPOTENCY_TRUE):
        if idempotency.get(key) is not True:
            blockers.append(f"idempotency_policy {key} must be true")

    evidence = _dict(data.get("evidence_policy"))
    for key in sorted(REQUIRED_EVIDENCE_TRUE):
        if evidence.get(key) is not True:
            blockers.append(f"evidence_policy {key} must be true")

    safety = _dict(data.get("side_effect_safety"))
    for key, value in sorted(safety.items()):
        if value is not False:
            blockers.append(f"side_effect_safety {key} must be false")

    for key, value in sorted(_dict(data.get("business_continuity")).items()):
        if value is not True:
            blockers.append(f"business_continuity {key} must be true")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE:
        blockers.append(f"next_bundle.recommended_next_step must be {NEXT_BUNDLE}")
    if next_bundle.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"next_bundle.route_family must be {ROUTE_FAMILY}")

    if state.get("current_phase") != "phase_5_external_adapter":
        blockers.append("phase_execution_state.current_phase must remain phase_5_external_adapter")
    if state.get("active_candidate") != ROUTE_FAMILY:
        blockers.append(f"phase_execution_state.active_candidate must be {ROUTE_FAMILY}")
    if state.get("last_merged_pr") != "#726":
        blockers.append("phase_execution_state.last_merged_pr must be #726")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append(f"phase_execution_state.recommended_next_pr must be {NEXT_BUNDLE}")
    if set(_list(state.get("next_allowed_actions"))) != {NEXT_BUNDLE}:
        blockers.append(f"phase_execution_state.next_allowed_actions must be {[NEXT_BUNDLE]}")
    if COMPLETED_STEP not in set(_list(state.get("completed_steps"))):
        blockers.append(f"phase_execution_state.completed_steps missing {COMPLETED_STEP}")

    for claim in sorted(FORBIDDEN_DOC_CLAIMS):
        if claim in doc_text:
            blockers.append(f"doc contains forbidden claim: {claim}")

    blockers.extend(_runner_static_report())

    changed, change_warnings = _changed_files()
    warnings.extend(change_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5N allowlist: {unexpected}")
    forbidden_exact = sorted(FORBIDDEN_EXACT_CHANGED & changed)
    if forbidden_exact:
        blockers.append(f"changed forbidden exact files: {forbidden_exact}")
    forbidden_prefix = sorted(path for path in changed if any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES))
    if forbidden_prefix:
        blockers.append(f"changed forbidden runtime/deploy files: {forbidden_prefix}")

    details["changed_files"] = sorted(changed)
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
        "# Phase 5N OAuth Identity Adapter Contract Check",
        "",
        f"- overall: {report.get('overall')}",
        f"- ok: {str(report.get('ok')).lower()}",
        "",
        "## Blockers",
        *(f"- {item}" for item in report.get("blockers", []) or ["none"]),
        "",
        "## Warnings",
        *(f"- {item}" for item in report.get("warnings", []) or ["none"]),
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 5N OAuth identity adapter contract bundle.")
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
