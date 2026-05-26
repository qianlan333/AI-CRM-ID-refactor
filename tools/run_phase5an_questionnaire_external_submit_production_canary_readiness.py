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
    "AICRM_PHASE5AN_QUESTIONNAIRE_PRODUCTION_CANARY_PLANNING_APPROVED": "not_executed_missing_production_canary_planning_approval",
    "AICRM_PHASE5AN_QUESTIONNAIRE_PRODUCTION_CONFIG_REVIEWED": "not_executed_missing_production_config_review",
    "AICRM_PHASE5AN_QUESTIONNAIRE_TARGET_POLICY_REVIEWED": "not_executed_missing_target_policy_review",
    "AICRM_PHASE5AN_QUESTIONNAIRE_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5AN_QUESTIONNAIRE_TAG_WRITEBACK_POLICY_REVIEWED": "not_executed_missing_tag_writeback_policy_review",
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


def _redact(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "<redacted>" if len(text) <= 8 else f"{text[:3]}...{text[-3:]}"


def _staging_ok(evidence: dict[str, Any]) -> bool:
    status = str(evidence.get("result_status") or "")
    return bool(evidence) and not status.startswith("not_executed") and evidence.get("production_public_submit_write_executed") is False and evidence.get("production_identity_write_executed") is False and evidence.get("production_tag_write_executed") is False and isinstance(evidence.get("side_effect_safety"), dict)


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
    if not args.slug:
        missing.append("not_executed_missing_slug")
    if not args.submission_id:
        missing.append("not_executed_missing_submission_id")
    if args.batch_submit:
        missing.append("not_executed_batch_submit_forbidden")
    if args.batch_tag_write:
        missing.append("not_executed_batch_tag_write_forbidden")
    for attr, status in (
        ("confirm_no_production_owner_switch", "not_executed_missing_confirm_no_production_owner_switch"),
        ("confirm_no_production_write", "not_executed_missing_confirm_no_production_write"),
        ("confirm_no_production_tag_write", "not_executed_missing_confirm_no_production_tag_write"),
        ("confirm_no_outbound_send", "not_executed_missing_confirm_no_outbound_send"),
        ("confirm_single_approved_target", "not_executed_missing_confirm_single_approved_target"),
    ):
        if not getattr(args, attr):
            missing.append(status)
    request_hash = _hash({"slug": args.slug or "", "submission_id": args.submission_id or "", "idempotency_key": args.idempotency_key or ""})
    return {
        "ok": not missing,
        "mode": "questionnaire_external_submit_production_canary_readiness",
        "result_status": "production_canary_readiness_ready_no_execution" if not missing else missing[0],
        "ready_for_phase5ao_family_acceptance": not missing,
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "live_oauth_callback_cutover_executed": False,
        "outbound_send_executed": False,
        "batch_submit_executed": False,
        "batch_tag_write_executed": False,
        "single_submit_target": bool(args.slug and args.submission_id),
        "slug_redacted": _redact(args.slug),
        "submission_id_redacted": _redact(args.submission_id),
        "idempotency_key": args.idempotency_key or "",
        "request_hash": request_hash,
        "cleanup_runner": "tools/run_phase5an_questionnaire_external_submit_production_canary_cleanup.py",
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "production_public_submit_write_executed": False,
            "production_identity_write_executed": False,
            "production_tag_write_executed": False,
            "live_oauth_callback_cutover_executed": False,
            "outbound_send_executed": False,
            "batch_tag_write_executed": False,
        },
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = ("ok", "result_status", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed", "outbound_send_executed")
    Path(path).write_text("# Phase 5AN Questionnaire Production Canary Readiness\n\n" + "\n".join(f"- {key}: {report[key]}" for key in fields) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--slug")
    parser.add_argument("--submission-id")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--batch-submit", action="store_true")
    parser.add_argument("--batch-tag-write", action="store_true")
    parser.add_argument("--confirm-no-production-owner-switch", action="store_true")
    parser.add_argument("--confirm-no-production-write", action="store_true")
    parser.add_argument("--confirm-no-production-tag-write", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--confirm-single-approved-target", action="store_true")
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
