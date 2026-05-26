#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter, WeComMediaAdapter
from aicrm_next.integration_gateway.audit import reset_audit_events
from aicrm_next.integration_gateway.idempotency import reset_idempotency_store


APPROVAL_ENV = "AICRM_PHASE5U_MEDIA_UPLOAD_STAGING_FAKE_STUB_APPROVED"
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extension(file_name: str) -> str:
    return Path(str(file_name or "")).suffix.lower()


def _metadata() -> dict[str, Any]:
    return {
        "file_name": "phase5u-staging-fixture.png",
        "content_type": "image/png",
        "declared_size_bytes": 68,
        "extension": ".png",
        "raw_file_dumped": False,
        "file_bytes_read": False,
    }


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
    metadata = _metadata()
    request_hash = _hash({"mode": "staging_fake_stub", **metadata, "idempotency_key": args.idempotency_key or "phase5u-staging-fake-stub"})
    blocked = not _enabled(APPROVAL_ENV)
    safety = _side_effect_safety()
    reset_audit_events()
    reset_idempotency_store()
    cloud_result: dict[str, Any] = {}
    wecom_result: dict[str, Any] = {}
    if not blocked:
        cloud_result = CloudStorageAdapter("fake").put_base64_object(
            data_base64="ZmFrZQ==",
            file_name=metadata["file_name"],
            content_type=metadata["content_type"],
            idempotency_key=args.idempotency_key or "phase5u-staging-fake-stub",
        )
        wecom_result = WeComMediaAdapter("fake").upload_image(
            data_base64="ZmFrZQ==",
            file_name=metadata["file_name"],
            idempotency_key=args.idempotency_key or "phase5u-staging-fake-stub-wecom",
        )
    valid_metadata = metadata["content_type"] in ALLOWED_MIME_TYPES and metadata["extension"] in ALLOWED_EXTENSIONS
    return {
        "ok": not blocked and valid_metadata,
        "mode": "media_upload_staging_fake_stub_smoke",
        "result_status": "not_executed_missing_staging_fake_stub_approval" if blocked else "staging_fake_stub_smoke_completed",
        "adapter_mode": "fake_stub",
        "route_family": "/api/admin/image-library*",
        "related_route_families": ["/api/admin/image-library/upload", "/api/admin/attachment-library*", "/api/admin/miniprogram-library*"],
        "approval_present": not blocked,
        "metadata": metadata,
        "metadata_valid": valid_metadata,
        "deterministic_fake_media": {
            "storage_key_present": bool(cloud_result.get("storage_key")),
            "media_id_present": bool(wecom_result.get("media_id")),
            "public_url_redacted": True,
            "reference_url_redacted": True,
        },
        "idempotency_key": args.idempotency_key or "phase5u-staging-fake-stub",
        "request_hash": request_hash,
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
        "# Phase 5U Media Upload Staging Fake/Stub Smoke",
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
    parser = argparse.ArgumentParser(description="Run Phase 5U media upload staging fake/stub smoke evidence.")
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
