#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Json = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_INCLUDED_ROUTES = {
    "GET /admin/image-library",
    "GET /api/admin/image-library",
    "GET /admin/attachment-library",
    "GET /api/admin/attachment-library",
    "GET /admin/miniprogram-library",
    "GET /api/admin/miniprogram-library",
}

REQUIRED_WRITE_EXCLUSIONS = {
    "POST /api/admin/image-library",
    "POST /api/admin/image-library/from-url",
    "POST /api/admin/image-library/from-base64",
    "PUT /api/admin/image-library/{image_id}",
    "DELETE /api/admin/image-library/{image_id}",
    "POST /api/admin/attachment-library",
    "PUT /api/admin/attachment-library/{attachment_id}",
    "DELETE /api/admin/attachment-library/{attachment_id}",
    "POST /api/admin/miniprogram-library",
    "PUT /api/admin/miniprogram-library/{item_id}",
    "DELETE /api/admin/miniprogram-library/{item_id}",
}

REQUIRED_SCREENSHOT_ROUTES = {
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
}

FALSE_SAFETY_FIELDS = {
    "production_config_modified",
    "old_write_endpoints_executed",
    "cloud_storage_upload_executed",
    "external_upload_executed",
    "wecom_media_upload_executed",
    "real_traffic_cutover_executed",
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


def _route_set(routes: Any) -> set[str]:
    return {item for item in routes if isinstance(item, str)} if isinstance(routes, list) else set()


def _safety_from_reports(*reports: Json) -> Json:
    safety: Json = {}
    for report in reports:
        source = report.get("side_effect_safety")
        if isinstance(source, dict):
            safety.update(source)
    return safety


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


def build_readiness_report(args: argparse.Namespace) -> Json:
    media_smoke = _load_json(args.media_smoke_json, label="media smoke")
    media_parity = _load_json(args.media_parity_json, label="media parity")
    batch_rehearsal = _load_json(args.batch_rehearsal_json, label="batch rehearsal")
    screenshot = _check_screenshot_baseline(args.route_status_json)

    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_evidence: list[Json] = []

    if not _is_pass(media_smoke):
        blockers.append({"reason": "media_smoke_not_pass", "source": args.media_smoke_json})
    if _as_list(media_smoke.get("blockers")):
        blockers.append({"reason": "media_smoke_has_blockers", "items": media_smoke.get("blockers")})
    if not _is_pass(media_parity):
        blockers.append({"reason": "media_parity_not_pass", "source": args.media_parity_json})
    if _as_list(media_parity.get("blockers")):
        blockers.append({"reason": "media_parity_has_blockers", "items": media_parity.get("blockers")})
    if batch_rehearsal.get("recommendation") != "GO" or batch_rehearsal.get("ok") is not True:
        blockers.append({"reason": "batch_rehearsal_not_go", "source": args.batch_rehearsal_json})

    included_routes = _route_set(batch_rehearsal.get("included_routes"))
    excluded_routes = _route_set(batch_rehearsal.get("excluded_routes"))
    missing_included = sorted(REQUIRED_INCLUDED_ROUTES - included_routes)
    extra_non_get = sorted(route for route in included_routes if not route.startswith("GET "))
    missing_excluded = sorted(REQUIRED_WRITE_EXCLUSIONS - excluded_routes)
    if missing_included:
        blockers.append({"reason": "missing_required_included_routes", "routes": missing_included})
    if extra_non_get:
        blockers.append({"reason": "non_get_route_included", "routes": extra_non_get})
    if missing_excluded:
        blockers.append({"reason": "missing_write_exclusions", "routes": missing_excluded})

    safety = _safety_from_reports(media_smoke, batch_rehearsal)
    for field in sorted(FALSE_SAFETY_FIELDS):
        if safety.get(field) is True:
            blockers.append({"reason": "side_effect_safety_violation", "field": field})
        elif field not in safety:
            warnings.append({"reason": "side_effect_safety_field_missing", "field": field})
    if safety.get("default_endpoints_get_only") is not True:
        blockers.append({"reason": "default_endpoints_not_get_only"})

    rollback = batch_rehearsal.get("rollback_dry_run")
    if not isinstance(rollback, dict):
        blockers.append({"reason": "rollback_dry_run_missing"})
    else:
        if rollback.get("route_flag_rollback_instruction") != "AICRM_NEXT_ROUTE_MEDIA_READONLY=false":
            blockers.append({"reason": "rollback_instruction_missing_or_wrong"})
        if rollback.get("expected_owner_after_rollback") != "old Flask":
            blockers.append({"reason": "rollback_owner_not_old_flask"})

    route_flags = batch_rehearsal.get("route_flags") if isinstance(batch_rehearsal.get("route_flags"), dict) else {}
    if route_flags.get("AICRM_NEXT_ROUTE_MEDIA_WRITES") is not False:
        blockers.append({"reason": "media_writes_flag_not_disabled"})
    if route_flags.get("AICRM_NEXT_EXTERNAL_CLOUD_STORAGE") is not False:
        blockers.append({"reason": "cloud_storage_flag_not_disabled"})
    if route_flags.get("AICRM_NEXT_EXTERNAL_WECOM_MEDIA") is not False:
        blockers.append({"reason": "wecom_media_flag_not_disabled"})

    if not screenshot["ok"]:
        blockers.append({"reason": "screenshot_baseline_not_ready", "result": screenshot})
    if not Path(args.media_smoke_json).exists():
        missing_evidence.append({"reason": "media_smoke_json_missing", "path": args.media_smoke_json})
    if not Path(args.media_parity_json).exists():
        missing_evidence.append({"reason": "media_parity_json_missing", "path": args.media_parity_json})
    if not Path(args.batch_rehearsal_json).exists():
        missing_evidence.append({"reason": "batch_rehearsal_json_missing", "path": args.batch_rehearsal_json})

    readiness_status = "canary_plan_ready" if not blockers else "not_ready"
    return {
        "ok": not blockers,
        "run_time": _utc_now(),
        "readiness_status": readiness_status,
        "recommendation": "GO_TO_STAGING_CANARY_SIGNOFF" if not blockers else "NO_GO",
        "source_reports": {
            "media_smoke_json": args.media_smoke_json,
            "media_parity_json": args.media_parity_json,
            "batch_rehearsal_json": args.batch_rehearsal_json,
            "route_status_json": args.route_status_json,
        },
        "included_routes": sorted(included_routes),
        "excluded_routes": sorted(excluded_routes),
        "side_effect_safety": safety,
        "rollback_dry_run": rollback or {},
        "screenshot_baseline": screenshot,
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
        "# Batch 1 Media Canary Readiness Report",
        "",
        f"- run_time: `{report['run_time']}`",
        f"- readiness_status: `{report['readiness_status']}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- ok: `{report['ok']}`",
        "",
        "## Source Reports",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in report["source_reports"].items())
    lines.extend(["", "## Side Effect Safety"])
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(report["side_effect_safety"].items()))
    lines.extend(["", "## Rollback Dry Run"])
    if report["rollback_dry_run"]:
        lines.extend(f"- {key}: `{value}`" for key, value in report["rollback_dry_run"].items())
    else:
        lines.append("- missing")
    lines.extend(["", "## Blockers"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Missing Evidence"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["missing_evidence"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Batch 1 Media Library readonly canary readiness from existing reports.")
    parser.add_argument("--media-smoke-json", required=True)
    parser.add_argument("--media-parity-json", required=True)
    parser.add_argument("--batch-rehearsal-json", required=True)
    parser.add_argument(
        "--route-status-json",
        default=str(PROJECT_ROOT / "artifacts" / "frontend_screenshots" / "route_status.json"),
        help="Frontend screenshot route status JSON.",
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
