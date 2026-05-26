#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import run_phase5al_questionnaire_external_submit_live_staging_evidence as phase5al


REQUIRED_ENV = [
    *phase5al.REQUIRED_ENV,
    "AICRM_PHASE5AM_QUESTIONNAIRE_STAGING_CANARY_APPROVED",
    "AICRM_PHASE5AM_QUESTIONNAIRE_STAGING_TARGET_APPROVED",
]


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip() == "1"


def _redact(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "<redacted>" if len(text) <= 8 else f"{text[:3]}...{text[-3:]}"


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.execute_staging_canary:
        missing.append("not_executed_missing_execute_staging_canary")
    if args.execute_staging_canary:
        for env_name in REQUIRED_ENV:
            if not _enabled(env_name):
                missing.append(f"not_executed_missing_{env_name.lower()}")
        for attr, status in (
            ("confirm_live_call", "not_executed_missing_confirm_live_call"),
            ("confirm_staging_only", "not_executed_missing_confirm_staging_only"),
            ("confirm_approved_target", "not_executed_missing_confirm_approved_target"),
            ("confirm_no_production_write", "not_executed_missing_confirm_no_production_write"),
            ("confirm_no_outbound_send", "not_executed_missing_confirm_no_outbound_send"),
        ):
            if not getattr(args, attr):
                missing.append(status)
        if not args.idempotency_key:
            missing.append("not_executed_missing_idempotency_key")
        if not args.slug:
            missing.append("not_executed_missing_slug")
        if not args.submission_id:
            missing.append("not_executed_missing_submission_id")
        if args.batch_submit:
            missing.append("not_executed_batch_submit_forbidden")
        if args.batch_tag_write:
            missing.append("not_executed_batch_tag_write_forbidden")
    if missing:
        return _blocked(missing[0], missing, args)
    upstream_args = argparse.Namespace(
        dry_run_live_gate=False,
        execute_staging_live=True,
        confirm_live_call=args.confirm_live_call,
        confirm_staging_only=args.confirm_staging_only,
        confirm_no_production_write=args.confirm_no_production_write,
        confirm_no_outbound_send=args.confirm_no_outbound_send,
        idempotency_key=args.idempotency_key,
        slug=args.slug,
    )
    result = phase5al.build_report(upstream_args)
    request_hash = _hash({"slug": args.slug, "submission_id": args.submission_id, "idempotency_key": args.idempotency_key})
    return {
        **result,
        "mode": "questionnaire_external_submit_staging_live_canary_evidence",
        "result_status": result.get("result_status", "blocked"),
        "single_submit_attempt": True,
        "approved_target_confirmed": True,
        "slug_redacted": _redact(args.slug),
        "submission_id_redacted": _redact(args.submission_id),
        "idempotency_key": args.idempotency_key,
        "request_hash": request_hash,
        "cleanup_required": bool(result.get("provider_call_executed")),
        "cleanup_guidance": "Capture separate staging cleanup approval before reversing any staging artifact.",
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "route_owner_changed": False,
    }


def _blocked(status: str, missing: list[str], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "questionnaire_external_submit_staging_live_canary_evidence",
        "result_status": status,
        "missing_items": missing,
        "provider_call_executed": False,
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "live_oauth_callback_cutover_executed": False,
        "outbound_send_executed": False,
        "batch_submit_executed": False,
        "batch_tag_write_executed": False,
        "single_submit_attempt": True,
        "slug_redacted": _redact(getattr(args, "slug", "")),
        "submission_id_redacted": _redact(getattr(args, "submission_id", "")),
        "token_redacted": True,
        "secret_redacted": True,
        "cleanup_required": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "route_owner_changed": False,
        "side_effect_safety": {
            "production_public_submit_write_allowed": False,
            "production_identity_write_allowed": False,
            "production_tag_write_allowed": False,
            "live_oauth_callback_cutover_allowed": False,
            "outbound_send_allowed": False,
            "batch_tag_write_allowed": False,
        },
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "provider_call_executed", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed", "outbound_send_executed")
    Path(path).write_text("# Phase 5AM Questionnaire Staging Canary Evidence\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-staging-canary", action="store_true")
    parser.add_argument("--confirm-live-call", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-approved-target", action="store_true")
    parser.add_argument("--confirm-no-production-write", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--slug")
    parser.add_argument("--submission-id")
    parser.add_argument("--batch-submit", action="store_true")
    parser.add_argument("--batch-tag-write", action="store_true")
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
