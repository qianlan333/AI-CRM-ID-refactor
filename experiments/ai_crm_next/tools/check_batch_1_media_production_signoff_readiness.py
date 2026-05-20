#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Json = dict[str, Any]

REQUIRED_INCLUDED_ROUTES = {
    "GET /admin/image-library",
    "GET /api/admin/image-library",
    "GET /admin/attachment-library",
    "GET /api/admin/attachment-library",
    "GET /admin/miniprogram-library",
    "GET /api/admin/miniprogram-library",
}

REQUIRED_EXCLUDED_MARKERS = {
    "POST /api/admin/image-library",
    "POST /api/admin/image-library/from-url",
    "POST /api/admin/image-library/from-base64",
    "PUT /api/admin/image-library/{image_id}",
    "DELETE /api/admin/image-library/{image_id}",
    "attachment write routes",
    "miniprogram write routes",
    "cloud storage upload",
    "WeCom media upload",
}

REQUIRED_FALSE_SAFETY = {
    "production_config_modified",
    "old_write_endpoints_executed",
    "cloud_storage_upload_executed",
    "external_upload_executed",
    "wecom_media_upload_executed",
    "real_traffic_cutover_executed",
}

ALLOWED_TRUE_SAFETY = {"default_endpoints_get_only", "fake_writes_next_testclient_only"}


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


def _read_text(path: str, *, label: str) -> str:
    text_path = Path(path)
    if not text_path.exists():
        raise FileNotFoundError(f"{label} does not exist: {text_path}")
    return text_path.read_text(encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_pass(report: Json) -> bool:
    return report.get("ok") is True or str(report.get("overall", "")).upper() == "PASS"


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    if start_marker not in text:
        return ""
    start = text.index(start_marker)
    if not end_marker:
        return text[start:]
    if end_marker not in text[start:]:
        return text[start:]
    end = text.index(end_marker, start)
    return text[start:end]


def _contains_any_write_route(section: str) -> bool:
    return any(method in section for method in ("POST ", "PUT ", "DELETE ", "PATCH "))


def _side_effect_safety(*reports: Json) -> Json:
    safety: Json = {}
    for report in reports:
        source = report.get("side_effect_safety")
        if isinstance(source, dict):
            safety.update(source)
    return safety


def _check_packet(text: str) -> tuple[list[Json], list[Json]]:
    blockers: list[Json] = []
    warnings: list[Json] = []

    required_markers = [
        "target batch | Batch 1 Media readonly",
        "target status | `pending_human_signoff`",
        "production execution | not executed",
        "canary type | readonly route-level canary",
        "cloud storage disabled",
        "WeCom media disabled",
        "write routes | excluded",
        "Proposed only",
        "Do not apply without human approval",
        "No secrets or production hosts",
        "approve production canary | pending_human_signoff",
        "Rollback owner",
        "## G. Stop Conditions",
        "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
    ]
    for marker in required_markers:
        if marker not in text:
            blockers.append({"reason": "signoff_packet_marker_missing", "marker": marker})

    included = _extract_section(text, "Included readonly routes:", "Excluded routes and operations:")
    missing_included = sorted(route for route in REQUIRED_INCLUDED_ROUTES if route not in included)
    if missing_included:
        blockers.append({"reason": "missing_required_included_routes", "routes": missing_included})
    if _contains_any_write_route(included):
        blockers.append({"reason": "write_route_included_in_readonly_section"})

    excluded = _extract_section(text, "Excluded routes and operations:", "## C. Required Evidence")
    missing_excluded = sorted(marker for marker in REQUIRED_EXCLUDED_MARKERS if marker not in excluded)
    if missing_excluded:
        blockers.append({"reason": "missing_required_excluded_routes", "routes": missing_excluded})

    forbidden_markers = ("production_approved", "approved_for_production: true")
    for marker in forbidden_markers:
        if marker in text:
            blockers.append({"reason": "forbidden_marker_present", "marker": marker})

    decision = _extract_section(text, "## I. Final Decision Block", "")
    if "| approve production canary | yes" in decision.lower() or "| approve production canary | true" in decision.lower():
        blockers.append({"reason": "final_decision_pre_approved"})
    if "pending_human_signoff" not in decision:
        blockers.append({"reason": "final_decision_not_pending"})

    if "http://prod" in text.lower() or "https://prod" in text.lower() or "prod.example" in text.lower():
        blockers.append({"reason": "production_host_present"})
    for secret_marker in ("secret=", "password=", "api_key=", "token="):
        if secret_marker in text.lower():
            blockers.append({"reason": "secret_marker_present", "marker": secret_marker})

    if "External adapter owner, if applicable" not in text:
        warnings.append({"reason": "external_adapter_owner_field_not_explicit"})

    return blockers, warnings


def _check_safety(safety: Json) -> list[Json]:
    blockers: list[Json] = []
    for key, value in sorted(safety.items()):
        if value is True and key not in ALLOWED_TRUE_SAFETY:
            blockers.append({"reason": "side_effect_safety_violation", "field": key})
    for field in sorted(REQUIRED_FALSE_SAFETY):
        if safety.get(field) is True:
            blockers.append({"reason": "required_false_safety_violation", "field": field})
    return blockers


def build_report(args: argparse.Namespace) -> Json:
    signoff_packet_text = _read_text(args.signoff_packet, label="signoff packet")
    approval_package_text = _read_text(args.approval_package, label="approval package")
    readiness = _load_json(args.readiness_json, label="approval readiness")
    media_smoke = _load_json(args.media_smoke_json, label="media smoke")
    media_parity = _load_json(args.media_parity_json, label="media parity")

    blockers: list[Json] = []
    warnings: list[Json] = []

    packet_blockers, packet_warnings = _check_packet(signoff_packet_text)
    blockers.extend(packet_blockers)
    warnings.extend(packet_warnings)

    if "Batch 1 Media readonly" not in approval_package_text:
        blockers.append({"reason": "approval_package_missing_batch_1_media"})
    if "pending_human_signoff" not in approval_package_text:
        blockers.append({"reason": "approval_package_not_pending_human_signoff"})
    if "not a production cutover" not in approval_package_text:
        blockers.append({"reason": "approval_package_missing_no_cutover_statement"})
    if "production_approved" in approval_package_text:
        blockers.append({"reason": "approval_package_has_forbidden_marker"})

    if readiness.get("ok") is not True:
        blockers.append({"reason": "approval_checker_not_ok", "source": args.readiness_json})
    if readiness.get("approval_status") != "pending_human_signoff":
        blockers.append({"reason": "approval_status_not_pending_human_signoff", "value": readiness.get("approval_status")})
    if _as_list(readiness.get("blockers")):
        blockers.append({"reason": "approval_checker_has_blockers", "items": readiness.get("blockers")})
    if not _is_pass(media_smoke):
        blockers.append({"reason": "media_smoke_not_pass", "source": args.media_smoke_json})
    if _as_list(media_smoke.get("blockers")):
        blockers.append({"reason": "media_smoke_has_blockers", "items": media_smoke.get("blockers")})
    if not _is_pass(media_parity):
        blockers.append({"reason": "media_parity_not_pass", "source": args.media_parity_json})
    if _as_list(media_parity.get("blockers")):
        blockers.append({"reason": "media_parity_has_blockers", "items": media_parity.get("blockers")})

    safety = _side_effect_safety(readiness, media_smoke, media_parity)
    safety.setdefault("production_config_modified", False)
    safety.setdefault("real_traffic_cutover_executed", False)
    blockers.extend(_check_safety(safety))

    signoff_status = "pending_human_signoff"
    return {
        "ok": not blockers,
        "run_time": _utc_now(),
        "signoff_status": signoff_status,
        "recommended_next_action": "REQUEST_HUMAN_SIGNOFF" if not blockers else "NO_GO_FIX_BLOCKERS",
        "source_reports": {
            "signoff_packet": args.signoff_packet,
            "approval_package": args.approval_package,
            "readiness_json": args.readiness_json,
            "media_smoke_json": args.media_smoke_json,
            "media_parity_json": args.media_parity_json,
        },
        "target_batch": "media_readonly",
        "blockers": blockers,
        "warnings": warnings,
        "side_effect_safety": safety,
        "approval_checker_status": {
            "ok": readiness.get("ok"),
            "approval_status": readiness.get("approval_status"),
            "recommended_next_action": readiness.get("recommended_next_action"),
        },
    }


def write_json(report: Json, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(report: Json, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Batch 1 Media Production Signoff Readiness Report",
        "",
        f"- ok: `{report['ok']}`",
        f"- signoff_status: `{report['signoff_status']}`",
        f"- recommended_next_action: `{report['recommended_next_action']}`",
        f"- target_batch: `{report['target_batch']}`",
        f"- run_time: `{report['run_time']}`",
        "",
        "## Source Reports",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in report["source_reports"].items())
    lines.extend(["", "## Approval Checker Status"])
    lines.extend(f"- {key}: `{value}`" for key, value in report["approval_checker_status"].items())
    lines.extend(["", "## Side Effect Safety"])
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(report["side_effect_safety"].items()))
    lines.extend(["", "## Blockers"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Approval Boundary"])
    lines.append("- This checker does not approve production execution.")
    lines.append("- Passing status only means the packet can be submitted for human signoff.")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Batch 1 Media production canary human signoff readiness.")
    parser.add_argument("--signoff-packet", required=True)
    parser.add_argument("--approval-package", required=True)
    parser.add_argument("--readiness-json", required=True)
    parser.add_argument("--media-smoke-json", required=True)
    parser.add_argument("--media-parity-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_markdown(report, args.output_md)
    write_json(report, args.output_json)
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("signoff_status:", report["signoff_status"])
    print("recommended_next_action:", report["recommended_next_action"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
