#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    evidence = _load(args.staging_evidence_json)
    if not evidence:
        missing.append("not_executed_missing_staging_evidence")
    elif str(evidence.get("result_status", "")).startswith("not_executed"):
        missing.append("not_executed_invalid_staging_evidence")
    if not args.confirm_no_production_write:
        missing.append("not_executed_missing_confirm_no_production_write")
    if not args.confirm_no_production_tag_write:
        missing.append("not_executed_missing_confirm_no_production_tag_write")
    if not args.confirm_no_outbound_send:
        missing.append("not_executed_missing_confirm_no_outbound_send")
    ready = not missing
    return {
        "ok": ready,
        "mode": "questionnaire_external_submit_production_readiness_review",
        "ready_for_phase5an_production_canary_readiness": ready,
        "result_status": "production_readiness_review_ready" if ready else missing[0],
        "missing_items": missing,
        "evidence_summary": {
            "result_status": evidence.get("result_status") if evidence else None,
            "single_submit_attempt": evidence.get("single_submit_attempt") if evidence else None,
            "slug_redacted": evidence.get("slug_redacted") if evidence else None,
            "submission_id_redacted": evidence.get("submission_id_redacted") if evidence else None,
        },
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "live_oauth_callback_cutover_executed": False,
        "outbound_send_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed", "outbound_send_executed")
    Path(path).write_text("# Phase 5AM Questionnaire Production Readiness Review\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-write", action="store_true")
    parser.add_argument("--confirm-no-production-tag-write", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
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
