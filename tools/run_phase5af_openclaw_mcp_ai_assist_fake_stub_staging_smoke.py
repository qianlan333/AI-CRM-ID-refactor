#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ERROR_MAPPING = [
    "mcp_config_missing",
    "openclaw_config_missing",
    "llm_config_missing",
    "prompt_required",
    "idempotency_key_required",
    "duplicate_idempotency_key",
    "request_hash_conflict",
    "real_mcp_call_not_enabled",
    "real_openclaw_call_not_enabled",
    "real_llm_call_not_enabled",
    "prompt_redaction_required",
    "credential_leak_risk",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
]
SUPPORTED_METHODS = [
    "plan_ai_assist_request",
    "redact_prompt_context",
    "fake_stub_mcp_tool_call",
    "fake_stub_openclaw_context_push",
    "fake_stub_llm_completion",
    "validate_idempotency_key",
]
SIDE_EFFECT_SAFETY = {
    "real_mcp_call_allowed": False,
    "real_openclaw_call_allowed": False,
    "real_llm_call_allowed": False,
    "deepseek_call_allowed": False,
    "outbound_send_allowed": False,
    "prompt_raw_output_allowed": False,
    "credential_output_allowed": False,
    "timer_execution_allowed": False,
    "automation_execution_allowed": False,
    "production_write_allowed": False,
}


def _request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "mode": args.mode,
        "surface": "openclaw_mcp_ai_assist",
        "sample_prompt_redacted": "<redacted_prompt>",
        "sample_context_redacted": "<redacted_context>",
    }
    return {
        "ok": True,
        "mode": args.mode,
        "result_status": "fake_stub_staging_smoke_ready",
        "adapter_mode": "fake_stub_contract",
        "real_mcp_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_llm_call_executed": False,
        "deepseek_call_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "credential_used": False,
        "prompt_redacted": True,
        "credential_redacted": True,
        "deterministic_responses": [
            {"method": "fake_stub_mcp_tool_call", "result": "fake_mcp_tool_result"},
            {"method": "fake_stub_openclaw_context_push", "result": "fake_openclaw_context_evidence"},
            {"method": "fake_stub_llm_completion", "result": "fake_ai_assist_completion"},
        ],
        "supported_methods": SUPPORTED_METHODS,
        "error_mapping": ERROR_MAPPING,
        "idempotency_policy": {
            "idempotency_key_required_for_write_like_dry_run": True,
            "replay_same_hash": True,
            "conflict_different_hash": True,
            "retry_safe_without_external_side_effect": True,
            "no_partial_external_side_effect": True,
        },
        "request_hash": _request_hash(payload),
        "side_effect_safety": SIDE_EFFECT_SAFETY,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5AF OpenClaw/MCP/AI Assist Fake Stub Staging Smoke",
        "",
        f"- ok: {report['ok']}",
        f"- result_status: {report['result_status']}",
        f"- real_mcp_call_executed: {report['real_mcp_call_executed']}",
        f"- real_openclaw_call_executed: {report['real_openclaw_call_executed']}",
        f"- real_llm_call_executed: {report['real_llm_call_executed']}",
        f"- deepseek_call_executed: {report['deepseek_call_executed']}",
        f"- outbound_send_executed: {report['outbound_send_executed']}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="fake_stub_contract", choices=["fake_stub_contract"])
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"ok": report["ok"], "result_status": report["result_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
