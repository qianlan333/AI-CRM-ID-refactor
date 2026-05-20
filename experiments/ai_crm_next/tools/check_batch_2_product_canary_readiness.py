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

REQUIRED_READ_NAMES = {
    "admin_products_page",
    "admin_products_list",
    "admin_product_detail",
    "public_product_page",
    "public_product_api",
}

REQUIRED_WRITE_EXCLUSIONS = {
    "POST /api/admin/wechat-pay/products",
    "PUT /api/admin/wechat-pay/products/{product_id}",
    "POST /api/admin/wechat-pay/products/{product_id}/enable",
    "POST /api/admin/wechat-pay/products/{product_id}/disable",
    "DELETE /api/admin/wechat-pay/products/{product_id}",
    "POST /api/checkout/wechat",
    "POST /api/checkout/alipay",
    "POST /api/wechat-pay/notify",
    "POST /api/alipay/notify",
}

REQUIRED_SCREENSHOT_ROUTES = {
    "/admin/wechat-pay/products",
    "/p/course-masked-001",
}

FALSE_SAFETY_FIELDS = {
    "old_write_endpoints_executed",
    "checkout_executed",
    "payment_provider_called",
    "external_payment_executed",
    "production_config_modified",
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


def _route_names(report: Json) -> set[str]:
    return {item.get("name") for item in _as_list(report.get("route_results")) if isinstance(item, dict) and isinstance(item.get("name"), str)}


def _non_get_routes(report: Json) -> list[Json]:
    return [
        {"name": item.get("name"), "method": item.get("method"), "path": item.get("path")}
        for item in _as_list(report.get("route_results"))
        if isinstance(item, dict) and item.get("method") != "GET"
    ]


def build_readiness_report(args: argparse.Namespace) -> Json:
    product_smoke = _load_json(args.product_smoke_json, label="product smoke")
    commerce_parity = _load_json(args.commerce_parity_json, label="commerce parity")
    screenshot = _check_screenshot_baseline(args.route_status_json)

    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_evidence: list[Json] = []

    if not _is_pass(product_smoke):
        blockers.append({"reason": "product_smoke_not_pass", "source": args.product_smoke_json})
    if _as_list(product_smoke.get("blockers")):
        blockers.append({"reason": "product_smoke_has_blockers", "items": product_smoke.get("blockers")})
    if not _is_pass(commerce_parity):
        blockers.append({"reason": "commerce_parity_not_pass", "source": args.commerce_parity_json})
    if _as_list(commerce_parity.get("blockers")):
        blockers.append({"reason": "commerce_parity_has_blockers", "items": commerce_parity.get("blockers")})

    route_names = _route_names(product_smoke)
    missing_routes = sorted(REQUIRED_READ_NAMES - route_names)
    if missing_routes:
        blockers.append({"reason": "missing_required_read_routes", "routes": missing_routes})
    non_get = _non_get_routes(product_smoke)
    if non_get:
        blockers.append({"reason": "non_get_route_in_default_smoke", "routes": non_get})

    checkout_endpoints = product_smoke.get("checkout_endpoints")
    if not isinstance(checkout_endpoints, list) or "/api/checkout/wechat" not in checkout_endpoints or "/api/checkout/alipay" not in checkout_endpoints:
        warnings.append({"reason": "checkout_exclusion_metadata_missing"})

    safety = _safety_from_reports(product_smoke)
    safety.setdefault("production_config_modified", False)
    safety.setdefault("real_traffic_cutover_executed", False)
    for field in sorted(FALSE_SAFETY_FIELDS):
        if safety.get(field) is True:
            blockers.append({"reason": "side_effect_safety_violation", "field": field})
        elif field not in safety:
            warnings.append({"reason": "side_effect_safety_field_missing", "field": field})
    if safety.get("default_endpoints_get_only") is not True:
        blockers.append({"reason": "default_endpoints_not_get_only"})
    if safety.get("checkout_endpoints_in_default_smoke") is not False:
        blockers.append({"reason": "checkout_in_default_smoke"})

    if not screenshot["ok"]:
        blockers.append({"reason": "screenshot_baseline_not_ready", "result": screenshot})

    if not Path(args.product_smoke_json).exists():
        missing_evidence.append({"reason": "product_smoke_json_missing", "path": args.product_smoke_json})
    if not Path(args.commerce_parity_json).exists():
        missing_evidence.append({"reason": "commerce_parity_json_missing", "path": args.commerce_parity_json})

    rollback = {
        "route_flag_rollback_instruction": "AICRM_NEXT_ROUTE_PRODUCT_READONLY=false",
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
            "product_smoke_json": args.product_smoke_json,
            "commerce_parity_json": args.commerce_parity_json,
            "route_status_json": args.route_status_json,
        },
        "required_read_route_names": sorted(REQUIRED_READ_NAMES),
        "excluded_routes": sorted(REQUIRED_WRITE_EXCLUSIONS),
        "side_effect_safety": safety,
        "rollback_dry_run": rollback,
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
        "# Batch 2 Product Canary Readiness Report",
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
    lines.extend(f"- {key}: `{value}`" for key, value in report["rollback_dry_run"].items())
    lines.extend(["", "## Blockers"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Missing Evidence"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["missing_evidence"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Batch 2 Product Management readonly canary readiness from existing reports.")
    parser.add_argument("--product-smoke-json", required=True)
    parser.add_argument("--commerce-parity-json", required=True)
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
