#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.questionnaire.external_submit_adapter import build_questionnaire_external_submit_fake_stub_adapter


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip() == "1"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not _enabled("AICRM_PHASE5AK_QUESTIONNAIRE_PRODUCTION_DRY_RUN_APPROVED"):
        missing.append("not_executed_missing_production_dry_run_approval")
    if not _enabled("AICRM_PHASE5AK_QUESTIONNAIRE_PRODUCTION_CONFIG_REVIEWED"):
        missing.append("not_executed_missing_production_config_review")
    if not args.dry_run:
        missing.append("not_executed_missing_dry_run")
    if not args.confirm_no_production_write:
        missing.append("not_executed_missing_confirm_no_production_write")
    adapter = build_questionnaire_external_submit_fake_stub_adapter()
    fake = adapter.deterministic_fake_public_submission()
    report = {
        "ok": not missing,
        "mode": "questionnaire_external_submit_fake_stub_production_dry_run",
        "result_status": "production_fake_stub_dry_run_ready" if not missing else missing[0],
        "missing_items": missing,
        "deterministic_submission": fake,
        "live_oauth_callback_cutover_executed": False,
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": {
            "production_public_submit_write_executed": False,
            "production_identity_write_executed": False,
            "production_tag_write_executed": False,
            "outbound_send_executed": False,
        },
    }
    if not missing:
        report["submit_evidence"] = adapter.dry_run_public_submit(slug=fake["slug"], answers=fake["answers"], identity=fake["identity"], operator="phase5ak_production_dry_run", idempotency_key=args.idempotency_key or "phase5ak-prod-dry-run")
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed")
    Path(path).write_text("# Phase 5AK Questionnaire Production Dry Run\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-production-write", action="store_true")
    parser.add_argument("--idempotency-key")
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
