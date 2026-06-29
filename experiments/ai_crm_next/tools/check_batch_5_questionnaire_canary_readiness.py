#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.doc_paths import experiment_doc_path

Json = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SMOKE_ROUTE_NAMES = {
    "admin_questionnaires_page",
    "admin_questionnaires_ui",
    "admin_list.default",
    "admin_detail.sample",
    "admin_preflight.default",
    "admin_latest_submit_debug.sample",
    "admin_export.sample",
    "public_page.sample",
    "public_get.sample",
    "public_result.sample",
}

REQUIRED_SCREENSHOT_ROUTES = {
    "/admin/questionnaires",
    "/admin/questionnaires/ui",
    "/s/hxc-activation-v1",
}

FALSE_SAFETY_FIELDS = {
    "old_write_endpoints_executed",
    "old_submit_executed",
    "real_oauth_executed",
    "wecom_tag_executed",
    "external_webhook_executed",
    "next_fake_submit_executed",
    "production_config_modified",
    "real_traffic_cutover_executed",
}

FORBIDDEN_ROUTE_FRAGMENTS = {
    "/submit",
    "/oauth/start",
    "/oauth/callback",
    "/external-push",
    "/retry",
    "/webhook",
}

ACCEPTED_LEGACY_REASONS = {
    "legacy_admin_auth_redirect",
    "legacy_wechat_browser_gate",
    "legacy_missing_public_result_api",
    "legacy_missing_required_contract",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: str, *, label: str) -> Json:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"{label} JSON does not exist: {json_path}")
    with json_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} JSON must contain an object: {json_path}")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_pass(report: Json) -> bool:
    return report.get("ok") is True or str(report.get("overall", "")).upper() == "PASS"


def _safety_from_reports(*reports: Json) -> Json:
    safety: Json = {}
    for report in reports:
        source = report.get("side_effect_safety")
        if isinstance(source, dict):
            safety.update(source)
    return safety


def _smoke_route_names(report: Json) -> set[str]:
    return {
        item.get("name")
        for item in _as_list(report.get("route_results"))
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _route_items(report: Json) -> list[Json]:
    return [item for item in _as_list(report.get("route_results")) if isinstance(item, dict)]


def _non_get_routes(report: Json) -> list[Json]:
    findings: list[Json] = []
    for item in _route_items(report):
        method = item.get("method")
        if method != "GET":
            findings.append({"name": item.get("name"), "method": method, "path": item.get("path")})
    return findings


def _forbidden_routes(report: Json) -> list[Json]:
    findings: list[Json] = []
    for item in _route_items(report):
        path = str(item.get("path") or "")
        next_path = str(item.get("next_path") or "")
        old_path = str(item.get("old_path") or "")
        haystack = " ".join([path, next_path, old_path])
        matched = sorted(fragment for fragment in FORBIDDEN_ROUTE_FRAGMENTS if fragment in haystack)
        if matched:
            findings.append({"name": item.get("name"), "method": item.get("method"), "path": path, "matched": matched})
    return findings


def _unexpected_skipped(report: Json) -> list[Json]:
    unexpected: list[Json] = []
    for item in _as_list(report.get("skipped")):
        if not isinstance(item, dict):
            continue
        if item.get("reason") == "fake_submit_not_requested":
            continue
        unexpected.append(item)
    return unexpected


def _unexpected_legacy_drift(report: Json) -> list[Json]:
    unexpected: list[Json] = []
    for item in _as_list(report.get("legacy_drift")):
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or item.get("rule") or "")
        if reason in ACCEPTED_LEGACY_REASONS and item.get("next_satisfies_contract") is True:
            continue
        unexpected.append(item)
    return unexpected


def _check_screenshot_baseline(path: str) -> Json:
    route_status_path = Path(path)
    if not route_status_path.exists():
        return {"ok": False, "reason": "screenshot_route_status_missing", "path": str(route_status_path)}
    payload = _load_json(str(route_status_path), label="screenshot route_status")
    route_results = payload.get("route_results")
    if not isinstance(route_results, list):
        return {"ok": False, "reason": "route_results_missing", "path": str(route_status_path)}
    indexed = {item.get("route"): item for item in route_results if isinstance(item, dict)}
    missing = sorted(route for route in REQUIRED_SCREENSHOT_ROUTES if route not in indexed)
    failed = sorted(route for route in REQUIRED_SCREENSHOT_ROUTES if route in indexed and not indexed[route].get("ok"))
    return {
        "ok": not missing and not failed,
        "path": str(route_status_path),
        "required_routes": sorted(REQUIRED_SCREENSHOT_ROUTES),
        "missing_routes": missing,
        "failed_routes": failed,
        "summary": payload.get("summary", {}),
    }


def _check_real_pg_evidence(path: str) -> Json:
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {"ok": False, "reason": "real_pg_evidence_missing", "path": str(evidence_path)}
    text = evidence_path.read_text(encoding="utf-8")
    has_pass = "passed" in text.lower() or "PASS" in text
    return {"ok": has_pass, "path": str(evidence_path), "reason": "" if has_pass else "real_pg_pass_marker_missing"}


def _check_route_flags_doc(path: str) -> Json:
    doc_path = Path(path)
    if not doc_path.exists():
        return {"ok": False, "reason": "route_flags_doc_missing", "path": str(doc_path)}
    text = doc_path.read_text(encoding="utf-8")
    required = [
        "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true",
        "AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false",
        "AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false",
        "AICRM_NEXT_QUESTIONNAIRE_OAUTH=false",
        "AICRM_NEXT_EXTERNAL_WECOM_TAG=false",
        "AICRM_NEXT_EXTERNAL_WEBHOOK=false",
        "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false",
    ]
    missing = [item for item in required if item not in text]
    return {"ok": not missing, "path": str(doc_path), "missing": missing}


def build_readiness_report(args: argparse.Namespace) -> Json:
    questionnaire_smoke = _load_json(args.questionnaire_smoke_json, label="questionnaire smoke")
    questionnaire_parity = _load_json(args.questionnaire_parity_json, label="questionnaire parity")
    screenshot = _check_screenshot_baseline(args.route_status_json)
    real_pg = _check_real_pg_evidence(args.real_pg_evidence)
    route_flags = _check_route_flags_doc(args.route_flags_doc)

    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_evidence: list[Json] = []

    if not _is_pass(questionnaire_smoke):
        blockers.append({"reason": "questionnaire_smoke_not_pass", "source": args.questionnaire_smoke_json})
    if _as_list(questionnaire_smoke.get("blockers")):
        blockers.append({"reason": "questionnaire_smoke_has_blockers", "items": questionnaire_smoke.get("blockers")})
    if not _is_pass(questionnaire_parity):
        blockers.append({"reason": "questionnaire_parity_not_pass", "source": args.questionnaire_parity_json})
    if _as_list(questionnaire_parity.get("blockers")):
        blockers.append({"reason": "questionnaire_parity_has_blockers", "items": questionnaire_parity.get("blockers")})

    missing_smoke_routes = sorted(REQUIRED_SMOKE_ROUTE_NAMES - _smoke_route_names(questionnaire_smoke))
    if missing_smoke_routes:
        blockers.append({"reason": "missing_required_smoke_routes", "routes": missing_smoke_routes})
    for item in _route_items(questionnaire_smoke):
        if item.get("name") in REQUIRED_SMOKE_ROUTE_NAMES and item.get("status") == "FAIL":
            blockers.append({"reason": "required_readonly_route_failed", "route": item})
        if item.get("name") in REQUIRED_SMOKE_ROUTE_NAMES and item.get("status") == "SKIPPED":
            blockers.append({"reason": "required_readonly_route_skipped", "route": item})

    non_get = _non_get_routes(questionnaire_smoke)
    if non_get:
        blockers.append({"reason": "non_get_route_in_questionnaire_canary", "routes": non_get})
    forbidden = _forbidden_routes(questionnaire_smoke)
    if forbidden:
        blockers.append({"reason": "forbidden_questionnaire_route_in_canary", "routes": forbidden})

    unexpected_skipped = _unexpected_skipped(questionnaire_smoke)
    if unexpected_skipped:
        blockers.append({"reason": "unexpected_skipped_routes", "items": unexpected_skipped})
    unexpected_drift = _unexpected_legacy_drift(questionnaire_smoke)
    if unexpected_drift:
        warnings.append({"reason": "unexpected_legacy_drift", "items": unexpected_drift})

    safety = _safety_from_reports(questionnaire_smoke)
    safety.setdefault("production_config_modified", False)
    safety.setdefault("real_traffic_cutover_executed", False)
    for field in sorted(FALSE_SAFETY_FIELDS):
        if safety.get(field) is True:
            blockers.append({"reason": "side_effect_safety_violation", "field": field})
        elif field not in safety:
            warnings.append({"reason": "side_effect_safety_field_missing", "field": field})
    if safety.get("default_endpoints_get_only") is not True:
        blockers.append({"reason": "default_endpoints_not_get_only"})

    if not questionnaire_smoke.get("sample_questionnaire_id"):
        blockers.append({"reason": "sample_questionnaire_id_missing"})
    if not questionnaire_smoke.get("sample_slug"):
        blockers.append({"reason": "sample_slug_missing"})

    if not screenshot["ok"]:
        blockers.append({"reason": "screenshot_baseline_not_ready", "result": screenshot})
    if not real_pg["ok"]:
        blockers.append({"reason": "real_pg_evidence_not_ready", "result": real_pg})
    if not route_flags["ok"]:
        blockers.append({"reason": "route_flags_not_ready", "result": route_flags})

    for label, path in {
        "questionnaire_smoke_json": args.questionnaire_smoke_json,
        "questionnaire_parity_json": args.questionnaire_parity_json,
    }.items():
        if not Path(path).exists():
            missing_evidence.append({"reason": label + "_missing", "path": path})

    legacy_drift = [
        item
        for item in _as_list(questionnaire_smoke.get("legacy_drift"))
        if isinstance(item, dict)
        and item.get("next_satisfies_contract") is True
        and str(item.get("reason") or item.get("rule") or "") in ACCEPTED_LEGACY_REASONS
    ]
    rollback = {
        "route_flag_rollback_instruction": "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false",
        "expected_owner_after_rollback": "old Flask",
        "rollback_verified": "dry-run only",
        "production_config_modified": False,
    }

    readiness_status = "canary_plan_ready" if not blockers else "not_ready"
    return {
        "ok": not blockers,
        "run_time": _utc_now(),
        "readiness_status": readiness_status,
        "recommendation": "GO_TO_STAGING_CANARY_SIGNOFF" if not blockers else "NO_GO",
        "source_reports": {
            "questionnaire_smoke_json": args.questionnaire_smoke_json,
            "questionnaire_parity_json": args.questionnaire_parity_json,
            "route_status_json": args.route_status_json,
            "real_pg_evidence": args.real_pg_evidence,
            "route_flags_doc": args.route_flags_doc,
        },
        "required_smoke_route_names": sorted(REQUIRED_SMOKE_ROUTE_NAMES),
        "legacy_drift": legacy_drift,
        "side_effect_safety": safety,
        "rollback_dry_run": rollback,
        "screenshot_baseline": screenshot,
        "real_pg_evidence": real_pg,
        "route_flags": route_flags,
        "blockers": blockers,
        "warnings": warnings,
        "missing_evidence": missing_evidence,
    }


def write_json_report(report: Json, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Batch 5 Questionnaire Canary Readiness Report",
        "",
        f"- run_time: `{report['run_time']}`",
        f"- readiness_status: `{report['readiness_status']}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- ok: `{report['ok']}`",
        "",
        "## Source Reports",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in report["source_reports"].items())
    lines.extend(["", "## Legacy Drift"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["legacy_drift"]] or ["- none"])
    lines.extend(["", "## Side Effect Safety"])
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(report["side_effect_safety"].items()))
    lines.extend(["", "## Rollback Dry Run"])
    lines.extend(f"- {key}: `{value}`" for key, value in report["rollback_dry_run"].items())
    lines.extend(["", "## Blockers"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Missing Evidence"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["missing_evidence"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Batch 5 Questionnaire readonly canary readiness from existing reports.")
    parser.add_argument("--questionnaire-smoke-json", required=True)
    parser.add_argument("--questionnaire-parity-json", required=True)
    parser.add_argument(
        "--route-status-json",
        default=str(PROJECT_ROOT / "artifacts" / "frontend_screenshots" / "route_status.json"),
        help="Frontend screenshot route status JSON.",
    )
    parser.add_argument(
        "--real-pg-evidence",
        default=str(PROJECT_ROOT / "docs" / "real_postgres_integration_run.md"),
        help="Real local/test PostgreSQL integration evidence document.",
    )
    parser.add_argument(
        "--route-flags-doc",
        default=str(experiment_doc_path("batch_5_questionnaire_readonly_route_flags.md")),
        help="Batch 5 route flags dry-run document.",
    )
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_readiness_report(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_markdown_report(report, args.output_md)
    write_json_report(report, args.output_json)
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("readiness_status:", report["readiness_status"])
    print("recommendation:", report["recommendation"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
