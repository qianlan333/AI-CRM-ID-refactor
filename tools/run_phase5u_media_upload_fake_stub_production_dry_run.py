#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_provider_upload_executed": False,
        "wecom_media_upload_executed": False,
        "cloud_storage_upload_executed": False,
        "network_call_executed": False,
        "token_used": False,
        "provider_secret_used": False,
        "public_media_url_published": False,
        "raw_file_exposed": False,
        "destructive_delete_executed": False,
        "db_write_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.dry_run:
        missing.append("not_executed_missing_dry_run")
    if not args.confirm_no_live_upload:
        missing.append("not_executed_missing_confirm_no_live_upload")
    if not args.confirm_no_public_publish:
        missing.append("not_executed_missing_confirm_no_public_publish")
    safety = _side_effect_safety()
    request_hash = _hash({"mode": "production_fake_stub_dry_run", "dry_run": bool(args.dry_run), "idempotency_key": args.idempotency_key or "phase5u-production-dry-run"})
    return {
        "ok": not missing,
        "mode": "media_upload_production_fake_stub_dry_run",
        "result_status": "production_fake_stub_dry_run_ready" if not missing else missing[0],
        "route_family": "/api/admin/image-library*",
        "idempotency_key": args.idempotency_key or "phase5u-production-dry-run",
        "request_hash": request_hash,
        "missing_items": missing,
        "metadata_policy": {
            "allowed_mime_types": ["image/png", "image/jpeg", "image/webp", "application/pdf"],
            "allowed_extensions": [".png", ".jpg", ".jpeg", ".webp", ".pdf"],
            "max_size_bytes": 5242880,
            "raw_file_dump_allowed": False,
        },
        **safety,
        "side_effect_safety": safety,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5U Media Upload Production Fake/Stub Dry Run",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {report.get('result_status')}",
        f"- live_provider_upload_executed: {str(report.get('live_provider_upload_executed')).lower()}",
        f"- public_media_url_published: {str(report.get('public_media_url_published')).lower()}",
        f"- raw_file_exposed: {str(report.get('raw_file_exposed')).lower()}",
        f"- destructive_delete_executed: {str(report.get('destructive_delete_executed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5U media upload production fake/stub dry-run evidence.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-live-upload", action="store_true")
    parser.add_argument("--confirm-no-public-publish", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
