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


DOC = ROOT / "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STAGING_RUNNER = ROOT / "tools/run_phase5c_wecom_tag_live_staging_evidence.py"
PROD_RUNNER = ROOT / "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py"
TEST = ROOT / "tests/test_phase5c_wecom_tag_live_adapter_behind_flag.py"
LIVE_ADAPTER = ROOT / "aicrm_next/customer_tags/wecom_tag_live_adapter.py"
LIVE_GATEWAY = ROOT / "aicrm_next/integration_gateway/wecom_tag_live_gateway.py"
ROUTE_FAMILY = "/api/admin/wecom/tags*"
CAPABILITY_OWNER = "aicrm_next.customer_tags"
BUNDLE_TYPE = "phase_5_external_adapter_live_adapter_behind_flag_bundle"
NEXT_BUNDLE = "phase_5d_wecom_tag_staging_live_canary_evidence_bundle"
COMPLETED_STEP = "phase_5c_wecom_tag_live_adapter_behind_flag_completed"
REQUIRED_FLAGS = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED",
    "AICRM_WECOM_TAG_CORP_ID",
    "AICRM_WECOM_TAG_AGENT_SECRET",
}
REQUIRED_METHODS = {"list_wecom_tags_live", "mark_tags_live", "unmark_tags_live"}
REQUIRED_ERRORS = {
    "live_adapter_not_enabled",
    "live_call_not_approved",
    "wecom_config_missing",
    "idempotency_key_required",
    "duplicate_idempotency_key",
    "invalid_tag_id",
    "external_userid_missing",
    "wecom_live_call_failed",
    "forbidden_in_production_without_approval",
}
FORBIDDEN_DOC_CLAIMS = {
    "production live tag write enabled",
    "canary approved",
    "fallback removed",
    "production_compat changed",
    "delete_ready true",
    "delete_ready: true",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/customer_tags/api.py",
    "aicrm_next/customer_tags/application.py",
    "aicrm_next/customer_tags/dto.py",
    "aicrm_next/customer_tags/wecom_tag_adapter.py",
    "aicrm_next/customer_tags/wecom_tag_contract.py",
    "aicrm_next/customer_tags/wecom_tag_live_adapter.py",
    "aicrm_next/integration_gateway/wecom_tag_live_gateway.py",
    "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.md",
    "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/run_phase5c_wecom_tag_live_staging_evidence.py",
    "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py",
    "tools/check_phase5c_wecom_tag_live_adapter_behind_flag.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase5c_wecom_tag_live_adapter_behind_flag.py",
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
    "wecom_ability_service/db/migrations/",
)


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


def _live_adapter_blockers() -> list[str]:
    blockers: list[str] = []
    text = LIVE_ADAPTER.read_text(encoding="utf-8")
    for flag in sorted(REQUIRED_FLAGS):
        if flag not in text:
            blockers.append(f"live adapter must reference explicit flag {flag}")
    if "idempotency_key_required" not in text:
        blockers.append("live adapter must require idempotency key")
    if "side_effect_safety" not in text:
        blockers.append("live adapter must expose side_effect_safety")
    if "live_call_executed\": True" in text and "confirm_live_wecom_call" not in text:
        blockers.append("live adapter live execution must require explicit confirmation")
    if "os.getenv" not in text:
        blockers.append("live adapter must read explicit gates")
    missing_errors = sorted(REQUIRED_ERRORS - {error for error in REQUIRED_ERRORS if error in text})
    if missing_errors:
        blockers.append(f"live adapter missing error mappings: {missing_errors}")
    forbidden_calls = sorted({"send", "create_group_message_task", "send_welcome_msg", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(LIVE_ADAPTER))
    if forbidden_calls:
        blockers.append(f"live adapter contains forbidden side-effect calls: {forbidden_calls}")
    return blockers


def _gateway_blockers() -> list[str]:
    blockers: list[str] = []
    text = LIVE_GATEWAY.read_text(encoding="utf-8")
    if "urlopen" not in text or "/cgi-bin/externalcontact/get_corp_tag_list" not in text or "/cgi-bin/externalcontact/mark_tag" not in text:
        blockers.append("gateway must implement the live WeCom tag boundary without touching legacy business modules")
    if "AICRM_WECOM_TAG_CORP_ID" not in text or "AICRM_WECOM_TAG_AGENT_SECRET" not in text:
        blockers.append("gateway must use Phase 5C explicit CorpID/secret env keys")
    forbidden_calls = sorted({"send", "create_group_message_task", "send_welcome_msg", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(LIVE_GATEWAY))
    if forbidden_calls:
        blockers.append(f"gateway contains forbidden side-effect calls: {forbidden_calls}")
    return blockers


def _runner_blockers(path: Path, *, production_gate: bool = False) -> list[str]:
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8")
    for arg in ("--output-json", "--output-md"):
        if arg not in text:
            blockers.append(f"{path.relative_to(ROOT)} must support {arg}")
    for token in ("live_call_executed", "outbound_send_executed", "production_behavior_changed", "production_compat_changed", "fallback_removed"):
        if token not in text:
            blockers.append(f"{path.relative_to(ROOT)} must emit {token}")
    if path == STAGING_RUNNER:
        for token in ("AICRM_PHASE5C_WECOM_TAG_STAGING_LIVE_APPROVED", "--confirm-live-wecom-call", "--dry-run-live-gate", "--execute-live-staging"):
            if token not in text:
                blockers.append(f"staging runner missing required gate/mode token: {token}")
    if production_gate:
        if "build_live_wecom_tag_adapter" in text or "wecom_tag_live_gateway" in text:
            blockers.append("production dry-run gate must not import or execute live adapter/gateway")
        if "live_call_executed\": False" not in text:
            blockers.append("production dry-run gate must hard-code live_call_executed false")
    forbidden_calls = sorted({"send", "send_welcome_msg", "create_group_message_task", "oauth_callback", "payment", "upload_media", "openclaw", "mcp_dispatch"} & _call_names(path))
    if forbidden_calls:
        blockers.append(f"{path.relative_to(ROOT)} contains forbidden side-effect calls: {forbidden_calls}")
    return blockers


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    required = [DOC, PLAN_YAML, STATE, STAGING_RUNNER, PROD_RUNNER, TEST, LIVE_ADAPTER, LIVE_GATEWAY]
    for path in required:
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()

    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_5c_wecom_tag_live_adapter_behind_explicit_flag":
        blockers.append("status must be phase_5c_wecom_tag_live_adapter_behind_explicit_flag")
    if data.get("bundle_type") != BUNDLE_TYPE:
        blockers.append(f"bundle_type must be {BUNDLE_TYPE}")
    if data.get("route_family") != ROUTE_FAMILY:
        blockers.append(f"route_family must be {ROUTE_FAMILY}")
    if data.get("capability_owner") != CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {CAPABILITY_OWNER}")
    if data.get("integration_boundary") != "aicrm_next.integration_gateway":
        blockers.append("integration_boundary must be aicrm_next.integration_gateway")

    authorizations = _dict(data.get("authorizations"))
    if authorizations.get("live_wecom_adapter_code_authorized") is not True:
        blockers.append("live_wecom_adapter_code_authorized must be true")
    for field in (
        "live_wecom_call_by_default_authorized",
        "production_tag_write_authorized",
        "outbound_send_authorized",
        "production_owner_switch_authorized",
        "production_compat_change_authorized",
        "fallback_removal_authorized",
        "oauth_callback_cutover_authorized",
        "payment_behavior_authorized",
        "media_live_upload_authorized",
        "openclaw_mcp_live_call_authorized",
        "timer_execution_authorized",
        "automation_execution_authorized",
        "canary_approved",
        "delete_ready",
    ):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    live_adapter = _dict(data.get("live_adapter"))
    if live_adapter.get("default_enabled") is not False:
        blockers.append("live_adapter.default_enabled must be false")
    if REQUIRED_FLAGS - _strings(live_adapter.get("required_env")) - {"AICRM_WECOM_TAG_CORP_ID", "AICRM_WECOM_TAG_AGENT_SECRET"}:
        blockers.append("live_adapter.required_env missing required explicit flags")
    if REQUIRED_METHODS != _strings(live_adapter.get("methods")):
        blockers.append(f"live_adapter.methods must be exactly {sorted(REQUIRED_METHODS)}")
    for field, value in sorted(_dict(data.get("side_effect_safety")).items()):
        if value is not False:
            blockers.append(f"side_effect_safety.{field} must be false")
    staging = _dict(data.get("staging_evidence"))
    if staging.get("runner") != "tools/run_phase5c_wecom_tag_live_staging_evidence.py" or staging.get("default_blocked") is not True:
        blockers.append("staging_evidence runner/default_blocked invalid")
    if staging.get("dry_run_gate_supported") is not True or staging.get("execute_live_staging_requires_approval") is not True:
        blockers.append("staging_evidence must support dry-run gate and require approval for execution")
    production = _dict(data.get("production_dry_run_gate"))
    if production.get("runner") != "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py":
        blockers.append("production_dry_run_gate runner invalid")
    if production.get("live_call_executed") is not False or production.get("production_tag_write_executed") is not False:
        blockers.append("production_dry_run_gate must keep live_call/tag_write false")
    continuity = _dict(data.get("business_continuity"))
    for field in ("production_behavior_unchanged", "legacy_fallback_retained", "production_compat_unchanged"):
        if continuity.get(field) is not True:
            blockers.append(f"business_continuity.{field} must be true")
    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE or next_bundle.get("route_family") != ROUTE_FAMILY:
        blockers.append("next_bundle must recommend Phase 5D for /api/admin/wecom/tags*")

    if state.get("last_merged_pr") != "#713":
        blockers.append("phase state last_merged_pr must record #713")
    if state.get("last_attempted_action") != "phase_5c_wecom_tag_live_adapter_behind_flag_bundle":
        blockers.append("phase state last_attempted_action must be Phase 5C")
    if state.get("recommended_next_pr") != NEXT_BUNDLE or set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next action must advance to Phase 5D")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append(f"completed_steps must include {COMPLETED_STEP}")

    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    blockers.extend(_live_adapter_blockers())
    blockers.extend(_gateway_blockers())
    blockers.extend(_runner_blockers(STAGING_RUNNER))
    blockers.extend(_runner_blockers(PROD_RUNNER, production_gate=True))

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 5C allowed set: {unexpected}")
    forbidden_changed = sorted(
        path
        for path in changed
        if path in FORBIDDEN_EXACT_CHANGED or any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES)
    )
    if forbidden_changed:
        blockers.append(f"forbidden runtime/protected files changed: {forbidden_changed}")

    details["changed_files"] = sorted(changed)
    details["next_bundle"] = next_bundle
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "autopilot_deliverable": not blockers, "blockers": blockers, "warnings": warnings, "details": details}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 5C WeCom Tag Live Adapter Behind Flag Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Changed Files",
            *(f"- {item}" for item in report["details"].get("changed_files", [])),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
