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


def _approved() -> bool:
    return str(os.getenv("AICRM_PHASE5AK_QUESTIONNAIRE_STAGING_FAKE_STUB_APPROVED", "")).strip() == "1"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    adapter = build_questionnaire_external_submit_fake_stub_adapter()
    fake = adapter.deterministic_fake_public_submission()
    if not _approved():
        return {
            "ok": False,
            "mode": "questionnaire_external_submit_fake_stub_staging_smoke",
            "result_status": "not_executed_missing_staging_fake_stub_approval",
            "live_oauth_callback_cutover_executed": False,
            "production_public_submit_write_executed": False,
            "production_identity_write_executed": False,
            "production_tag_write_executed": False,
            "outbound_send_executed": False,
            "deterministic_submission": fake,
            "side_effect_safety": {"production_write_executed": False, "outbound_send_executed": False},
        }
    submit = adapter.dry_run_public_submit(slug=fake["slug"], answers=fake["answers"], identity=fake["identity"], operator="phase5ak_staging", idempotency_key=args.idempotency_key or "phase5ak-staging")
    identity = adapter.dry_run_identity_mapping(submission=fake, operator="phase5ak_staging", idempotency_key=(args.idempotency_key or "phase5ak-staging") + ":identity")
    tag = adapter.dry_run_tag_writeback(submission=fake, tag_ids=fake["tag_ids"], operator="phase5ak_staging", idempotency_key=(args.idempotency_key or "phase5ak-staging") + ":tag")
    return {
        "ok": bool(submit.get("ok") and identity.get("ok") and tag.get("ok")),
        "mode": "questionnaire_external_submit_fake_stub_staging_smoke",
        "result_status": "staging_fake_stub_evidence_ready",
        "submit_evidence": submit,
        "identity_evidence": identity,
        "tag_writeback_evidence": tag,
        "live_oauth_callback_cutover_executed": False,
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed")
    Path(path).write_text("# Phase 5AK Questionnaire Staging Fake/Stub\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
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
