#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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


def _acceptable(evidence: dict[str, Any]) -> bool:
    status = str(evidence.get("result_status") or "")
    if status.startswith("not_executed"):
        return False
    return (
        evidence.get("mode") == "media_upload_staging_live_canary_evidence"
        and evidence.get("public_media_url_published") is False
        and evidence.get("production_upload_executed") is False
        and evidence.get("destructive_delete_executed") is False
        and isinstance(evidence.get("side_effect_safety"), dict)
        and bool(evidence.get("file_name_redacted"))
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    evidence = _load_json(args.staging_evidence_json)
    if evidence is None:
        missing.append("not_executed_missing_staging_evidence")
    elif not _acceptable(evidence):
        missing.append("not_executed_invalid_staging_evidence")
    if not args.confirm_no_production_live_upload:
        missing.append("not_executed_missing_confirm_no_production_live_upload")
    if not args.confirm_no_public_publish:
        missing.append("not_executed_missing_confirm_no_public_publish")
    if not args.confirm_no_delete:
        missing.append("not_executed_missing_confirm_no_delete")
    return {
        "ok": not missing,
        "mode": "media_upload_production_live_readiness_review",
        "ready_for_phase5x_production_canary_readiness_execution": not missing,
        "result_status": "ready_for_phase5x_planning" if not missing else missing[0],
        "missing_items": missing,
        "evidence_summary": {
            "result_status": (evidence or {}).get("result_status"),
            "live_provider_upload_executed": bool((evidence or {}).get("live_provider_upload_executed")),
            "file_name_redacted": (evidence or {}).get("file_name_redacted"),
        },
        "production_live_upload_executed": False,
        "public_media_url_published": False,
        "production_media_publish_executed": False,
        "destructive_delete_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(f"# Phase 5W Media Production Readiness Review\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- production_live_upload_executed: false\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-live-upload", action="store_true")
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
