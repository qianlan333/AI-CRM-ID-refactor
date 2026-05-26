#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_report(args: argparse.Namespace) -> dict:
    missing = []
    if not args.dry_run:
        missing.append("not_executed_missing_dry_run")
    if not args.confirm_no_live_upload:
        missing.append("not_executed_missing_confirm_no_live_upload")
    if not args.confirm_no_public_publish:
        missing.append("not_executed_missing_confirm_no_public_publish")
    if not args.confirm_no_delete:
        missing.append("not_executed_missing_confirm_no_delete")
    return {
        "ok": not missing,
        "mode": "media_upload_live_production_dry_run_gate",
        "result_status": "production_live_gate_ready_no_upload" if not missing else missing[0],
        "production_live_upload_executed": False,
        "public_media_url_published": False,
        "production_media_publish_executed": False,
        "destructive_delete_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "production_live_upload_executed": False,
            "public_media_url_published": False,
            "destructive_delete_executed": False,
            "raw_file_exposed": False,
            "token_used": False,
            "provider_secret_used": False,
            "network_call_executed": False,
            "route_owner_changed": False,
            "production_compat_changed": False,
            "fallback_removed": False,
        },
    }


def _write_json(report: dict, path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict, path: str) -> None:
    Path(path).write_text(f"# Phase 5V Media Production Dry Run Gate\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- production_live_upload_executed: false\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-live-upload", action="store_true")
    parser.add_argument("--confirm-no-public-publish", action="store_true")
    parser.add_argument("--confirm-no-delete", action="store_true")
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
