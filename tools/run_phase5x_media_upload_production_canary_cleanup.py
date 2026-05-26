#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence = _load_json(args.canary_evidence_json)
    missing: list[str] = []
    if evidence is None:
        missing.append("not_executed_missing_canary_evidence")
    elif evidence.get("mode") != "media_upload_production_canary_readiness_execution":
        missing.append("not_executed_invalid_canary_evidence")
    if not _enabled("AICRM_PHASE5X_MEDIA_UPLOAD_PRODUCTION_CLEANUP_APPROVED"):
        missing.append("not_executed_missing_cleanup_approval")
    if not _enabled("AICRM_PHASE5X_MEDIA_UPLOAD_ROLLBACK_OWNER_APPROVED"):
        missing.append("not_executed_missing_rollback_owner")
    if not args.confirm_production_cleanup_reviewed:
        missing.append("not_executed_missing_confirm_cleanup_reviewed")
    if not args.confirm_same_file:
        missing.append("not_executed_missing_confirm_same_file")
    if not args.confirm_no_destructive_delete:
        missing.append("not_executed_missing_confirm_no_destructive_delete")
    if not args.confirm_no_batch_cleanup:
        missing.append("not_executed_missing_confirm_no_batch_cleanup")
    return {
        "ok": not missing,
        "mode": "media_upload_production_canary_cleanup",
        "result_status": "cleanup_review_ready_no_delete" if not missing else missing[0],
        "cleanup_executed": False,
        "destructive_delete_executed": False,
        "same_file_confirmed": bool(args.confirm_same_file),
        "batch_cleanup_executed": False,
        "public_media_url_unpublished": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "cleanup_executed": False,
            "destructive_delete_executed": False,
            "batch_cleanup_executed": False,
            "route_owner_changed": False,
            "production_compat_changed": False,
            "fallback_removed": False,
        },
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(f"# Phase 5X Media Canary Cleanup\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- destructive_delete_executed: false\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canary-evidence-json")
    parser.add_argument("--confirm-production-cleanup-reviewed", action="store_true")
    parser.add_argument("--confirm-same-file", action="store_true")
    parser.add_argument("--confirm-no-destructive-delete", action="store_true")
    parser.add_argument("--confirm-no-batch-cleanup", action="store_true")
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
