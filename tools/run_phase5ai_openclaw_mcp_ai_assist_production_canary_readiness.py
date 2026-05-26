#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_CALL_APPROVED": "not_executed_missing_live_call_approval",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_CONFIG_REVIEWED": "not_executed_missing_config_review",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_ENDPOINT_REVIEWED": "not_executed_missing_endpoint_review",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_CREDENTIAL_SOURCE_REVIEWED": "not_executed_missing_credential_source_review",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_PROMPT_REDACTION_CONFIRMED": "not_executed_missing_prompt_redaction_confirmed",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_NO_OUTBOUND_SEND_CONFIRMED": "not_executed_missing_no_outbound_send_env",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_NO_AUTOMATION_EXECUTION_CONFIRMED": "not_executed_missing_no_automation_execution_env",
    "AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_PRODUCTION_CANARY_APPROVED": "not_executed_missing_production_canary_approval",
    "AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_TARGET_APPROVED": "not_executed_missing_target_approval",
    "AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_OWNER_APPROVED": "not_executed_missing_owner_approval",
    "AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_PROMPT_REDACTION_REVIEWED": "not_executed_missing_prompt_redaction_review",
    "AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_CREDENTIAL_REDACTION_REVIEWED": "not_executed_missing_credential_redaction_review",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _redact(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "<redacted>" if len(text) <= 8 else f"{text[:4]}...{text[-4:]}"


def _staging_ok(evidence: dict[str, Any]) -> bool:
    status = str(evidence.get("result_status") or "")
    safety = evidence.get("side_effect_safety")
    return bool(evidence.get("ok")) and not status.startswith("not_executed") and isinstance(safety, dict) and evidence.get("outbound_send_executed") is False and evidence.get("automation_execution_executed") is False


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    staging = _load(args.staging_evidence_json)
    if not staging:
        missing.append("not_executed_missing_staging_evidence")
    elif not _staging_ok(staging):
        missing.append("not_executed_invalid_staging_evidence")
    for env_name, status in REQUIRED_ENV.items():
        if not _enabled(env_name):
            missing.append(status)
    if not args.idempotency_key:
        missing.append("not_executed_missing_idempotency_key")
    if not args.prompt and not args.tool_name:
        missing.append("not_executed_missing_prompt_or_tool")
    if args.prompt and args.tool_name:
        missing.append("not_executed_multiple_targets_forbidden")
    if args.prompt and "," in args.prompt:
        missing.append("not_executed_batch_prompt_forbidden")
    if args.tool_name and "," in args.tool_name:
        missing.append("not_executed_batch_tool_forbidden")
    for attr, status in (
        ("confirm_production_live_call", "not_executed_missing_confirm_production_live_call"),
        ("confirm_single_approved_target", "not_executed_missing_confirm_single_target"),
        ("confirm_redacted_evidence", "not_executed_missing_confirm_redacted_evidence"),
        ("confirm_credential_non_leakage", "not_executed_missing_confirm_credential_non_leakage"),
        ("confirm_no_outbound_send", "not_executed_missing_confirm_no_outbound_send"),
        ("confirm_no_automation_execution", "not_executed_missing_confirm_no_automation_execution"),
        ("confirm_rollback_owner_approved", "not_executed_missing_confirm_rollback_owner"),
    ):
        if not getattr(args, attr):
            missing.append(status)
    request_hash = _hash({"prompt_present": bool(args.prompt), "tool_name": args.tool_name or "", "idempotency_key": args.idempotency_key or ""})
    return {
        "ok": not missing,
        "mode": "openclaw_mcp_ai_assist_production_canary_readiness",
        "result_status": "production_canary_tooling_ready_blocked_gateway" if not missing else missing[0],
        "production_live_call_executed": False,
        "real_mcp_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_llm_call_executed": False,
        "deepseek_call_executed": False,
        "outbound_send_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
        "external_mutation_executed": False,
        "single_target": bool(args.prompt or args.tool_name) and not (args.prompt and args.tool_name),
        "prompt_redacted": _redact(args.prompt or ""),
        "tool_name_redacted": _redact(args.tool_name or ""),
        "credential_redacted": True,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": request_hash,
        "cleanup_runner": "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup.py",
        "rollback_required": bool(args.prompt or args.tool_name),
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "production_live_call_executed": False,
            "outbound_send_executed": False,
            "timer_execution_executed": False,
            "automation_execution_executed": False,
            "external_mutation_executed": False,
            "prompt_leak_detected": False,
            "credential_leak_detected": False,
        },
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = ("ok", "result_status", "production_live_call_executed", "outbound_send_executed", "automation_execution_executed")
    Path(path).write_text("# Phase 5AI OpenClaw MCP AI Assist Production Canary Readiness\n\n" + "\n".join(f"- {key}: {report[key]}" for key in fields) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--tool-name", default="")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-production-live-call", action="store_true")
    parser.add_argument("--confirm-single-approved-target", action="store_true")
    parser.add_argument("--confirm-redacted-evidence", action="store_true")
    parser.add_argument("--confirm-credential-non-leakage", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--confirm-no-automation-execution", action="store_true")
    parser.add_argument("--confirm-rollback-owner-approved", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report["ok"] else "BLOCKED", "ok": report["ok"], "status": report["result_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
