#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

Json = dict[str, Any]


@dataclass(frozen=True)
class SmokeEndpoint:
    name: str
    method: str
    path: str
    expected_status: int = 200
    required_keys: tuple[str, ...] = ()
    route_type: str = "api"
    side_effect_risk: str = "read"


READ_ENDPOINT_NAMES: tuple[str, ...] = (
    "admin_products_page",
    "admin_products_list",
    "admin_product_detail",
    "public_product_page",
    "public_product_api",
)

PRODUCT_LIST_KEYS = ("ok", "items", "total", "limit", "offset")
PRODUCT_DETAIL_KEYS = ("ok", "product")
PUBLIC_PRODUCT_KEYS = ("ok", "product")


CHECKOUT_ENDPOINTS: tuple[str, ...] = ("/api/checkout/wechat", "/api/checkout/alipay")


FAKE_PRODUCT_PAYLOAD: Json = {
    "product_code": "course_masked_gray",
    "title": "灰度商品 fixture",
    "description": "Product Management gray smoke fixture",
    "price_cents": 12300,
    "currency": "CNY",
    "enabled": True,
    "page_slug": "course-masked-gray",
    "cover_image_id": "image_masked_001",
    "detail_image_ids": ["image_masked_001"],
    "detail_sections": [{"title": "灰度详情", "body": "fixture only"}],
    "buy_button_text": "立即购买",
}


def _build_testclient():
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    return TestClient(create_app())


def _reset_commerce_state() -> None:
    from aicrm_next.commerce.repo import reset_commerce_fixture_state

    reset_commerce_fixture_state()


def _request_testclient(client: Any, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    response = client.request(method, path, json=payload)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _request_http(base_url: str, method: str, path: str) -> tuple[int, Json | str]:
    if method != "GET":
        raise RuntimeError("HTTP mode only supports GET for Product Management gray smoke.")
    with httpx.Client(timeout=10.0) as client:
        response = client.get(base_url.rstrip("/") + path)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _missing_keys(payload: Json | str, required_keys: tuple[str, ...]) -> list[str]:
    if not required_keys:
        return []
    if not isinstance(payload, dict):
        return list(required_keys)
    return [key for key in required_keys if key not in payload]


def _result(
    *,
    name: str,
    method: str,
    path: str,
    status_code: int,
    expected_status: int,
    payload: Json | str,
    required_keys: tuple[str, ...] = (),
    route_type: str = "api",
    side_effect_risk: str = "read",
) -> Json:
    missing = _missing_keys(payload, required_keys)
    ok = status_code == expected_status and not missing
    issues: list[Json] = []
    if status_code >= 500:
        issues.append({"severity": "blocker", "reason": "route_returned_5xx"})
    if status_code != expected_status:
        issues.append({"severity": "blocker", "reason": "unexpected_status", "expected": expected_status, "actual": status_code})
    for key in missing:
        issues.append({"severity": "blocker", "reason": "missing_required_key", "field": key})
    return {
        "name": name,
        "method": method,
        "path": path,
        "route_type": route_type,
        "side_effect_risk": side_effect_risk,
        "status_code": status_code,
        "expected_status": expected_status,
        "ok": ok,
        "missing_required_keys": missing,
        "issues": issues,
    }


def _fetch(args: argparse.Namespace, client: Any | None, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    if args.next_testclient:
        return _request_testclient(client, method, path, payload)
    return _request_http(args.next_base_url, method, path)


def _sample_product(client: Any | None, args: argparse.Namespace) -> tuple[str, str, list[Json]]:
    status_code, payload = _fetch(args, client, "GET", "/api/admin/wechat-pay/products")
    list_result = _result(
        name="admin_products_list",
        method="GET",
        path="/api/admin/wechat-pay/products",
        status_code=status_code,
        expected_status=200,
        payload=payload,
        required_keys=PRODUCT_LIST_KEYS,
        route_type="api",
        side_effect_risk="read",
    )
    if list_result["issues"]:
        return "", "", [list_result]
    if not isinstance(payload, dict) or not payload.get("items"):
        list_result["issues"].append({"severity": "blocker", "reason": "missing_sample_product"})
        list_result["ok"] = False
        return "", "", [list_result]
    product = payload["items"][0]
    return product["id"], product["page_slug"], [list_result]


def _run_read_smoke(args: argparse.Namespace, client: Any | None) -> list[Json]:
    results: list[Json] = []
    status_code, payload = _fetch(args, client, "GET", "/admin/wechat-pay/products")
    results.append(
        _result(
            name="admin_products_page",
            method="GET",
            path="/admin/wechat-pay/products",
            status_code=status_code,
            expected_status=200,
            payload=payload,
            route_type="page",
            side_effect_risk="read",
        )
    )
    product_id, page_slug, list_results = _sample_product(client, args)
    results.extend(list_results)
    if not product_id or not page_slug:
        return results
    status_code, payload = _fetch(args, client, "GET", f"/api/admin/wechat-pay/products/{product_id}")
    results.append(
        _result(
            name="admin_product_detail",
            method="GET",
            path=f"/api/admin/wechat-pay/products/{product_id}",
            status_code=status_code,
            expected_status=200,
            payload=payload,
            required_keys=PRODUCT_DETAIL_KEYS,
            route_type="api",
            side_effect_risk="read",
        )
    )
    status_code, payload = _fetch(args, client, "GET", f"/p/{page_slug}")
    results.append(
        _result(
            name="public_product_page",
            method="GET",
            path=f"/p/{page_slug}",
            status_code=status_code,
            expected_status=200,
            payload=payload,
            route_type="page",
            side_effect_risk="read",
        )
    )
    status_code, payload = _fetch(args, client, "GET", f"/api/products/{page_slug}")
    results.append(
        _result(
            name="public_product_api",
            method="GET",
            path=f"/api/products/{page_slug}",
            status_code=status_code,
            expected_status=200,
            payload=payload,
            required_keys=PUBLIC_PRODUCT_KEYS,
            route_type="api",
            side_effect_risk="read",
        )
    )
    return results


def _extract_product(payload: Json | str) -> Json:
    if not isinstance(payload, dict) or not isinstance(payload.get("product"), dict):
        raise RuntimeError("fake write response missing product")
    return payload["product"]


def _run_fake_writes(client: Any) -> list[Json]:
    results: list[Json] = []
    create_status, create_payload = _request_testclient(client, "POST", "/api/admin/wechat-pay/products", FAKE_PRODUCT_PAYLOAD)
    results.append(
        _result(
            name="product_create_fake_write",
            method="POST",
            path="/api/admin/wechat-pay/products",
            status_code=create_status,
            expected_status=200,
            payload=create_payload,
            required_keys=PRODUCT_DETAIL_KEYS,
            route_type="api",
            side_effect_risk="next_fake_write",
        )
    )
    product = _extract_product(create_payload)
    product_id = product["id"]
    update_payload = {**product, "title": "灰度商品 fixture 更新"}
    update_status, update_body = _request_testclient(client, "PUT", f"/api/admin/wechat-pay/products/{product_id}", update_payload)
    results.append(
        _result(
            name="product_update_fake_write",
            method="PUT",
            path=f"/api/admin/wechat-pay/products/{product_id}",
            status_code=update_status,
            expected_status=200,
            payload=update_body,
            required_keys=PRODUCT_DETAIL_KEYS,
            route_type="api",
            side_effect_risk="next_fake_write",
        )
    )
    for action in ["disable", "enable"]:
        status_code, body = _request_testclient(client, "POST", f"/api/admin/wechat-pay/products/{product_id}/{action}")
        results.append(
            _result(
                name=f"product_{action}_fake_write",
                method="POST",
                path=f"/api/admin/wechat-pay/products/{product_id}/{action}",
                status_code=status_code,
                expected_status=200,
                payload=body,
                required_keys=PRODUCT_DETAIL_KEYS,
                route_type="api",
                side_effect_risk="next_fake_write",
            )
        )
    delete_status, delete_body = _request_testclient(client, "DELETE", f"/api/admin/wechat-pay/products/{product_id}")
    results.append(
        _result(
            name="product_delete_fake_write",
            method="DELETE",
            path=f"/api/admin/wechat-pay/products/{product_id}",
            status_code=delete_status,
            expected_status=200,
            payload=delete_body,
            required_keys=("ok",),
            route_type="api",
            side_effect_risk="next_fake_write",
        )
    )
    return results


def run_smoke(args: argparse.Namespace) -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    skipped: list[Json] = []
    route_results: list[Json] = []
    side_effect_safety = {
        "old_write_endpoints_executed": False,
        "payment_provider_called": False,
        "checkout_executed": False,
        "external_payment_executed": False,
        "default_endpoints_get_only": True,
        "fake_writes_next_testclient_only": True,
        "checkout_endpoints_in_default_smoke": False,
    }

    if not args.next_testclient and not args.next_base_url:
        blockers.append({"reason": "missing_next_target", "message": "Use --next-testclient or --next-base-url."})
        return _report(args, route_results, blockers, warnings, skipped, side_effect_safety)
    if args.include_fake_writes and not args.next_testclient:
        blockers.append({"reason": "fake_writes_require_next_testclient", "message": "--include-fake-writes is allowed only with --next-testclient."})
        return _report(args, route_results, blockers, warnings, skipped, side_effect_safety)

    client = None
    if args.next_testclient:
        _reset_commerce_state()
        client = _build_testclient()

    route_results.extend(_run_read_smoke(args, client))
    for result in route_results:
        blockers.extend(result["issues"])

    if args.include_fake_writes:
        try:
            write_results = _run_fake_writes(client)
        except Exception as exc:
            blockers.append({"reason": "fake_write_exception", "message": str(exc)})
            write_results = []
        route_results.extend(write_results)
        for result in write_results:
            blockers.extend(result["issues"])
    else:
        skipped.append({"reason": "fake_writes_not_requested", "message": "POST/PUT/DELETE checks require --include-fake-writes and target Next TestClient only."})
        skipped.append({"reason": "checkout_not_in_scope", "message": "Checkout/payment endpoints are excluded from Product Management gray smoke."})

    if args.next_testclient:
        _reset_commerce_state()

    return _report(args, route_results, blockers, warnings, skipped, side_effect_safety)


def _report(
    args: argparse.Namespace,
    route_results: list[Json],
    blockers: list[Json],
    warnings: list[Json],
    skipped: list[Json],
    side_effect_safety: Json,
) -> Json:
    return {
        "ok": not blockers and all(item.get("ok", False) for item in route_results),
        "mode": "next-testclient" if args.next_testclient else "next-http",
        "next_base_url": "" if args.next_testclient else args.next_base_url,
        "include_fake_writes": bool(args.include_fake_writes),
        "checkout_endpoints": list(CHECKOUT_ENDPOINTS),
        "route_results": route_results,
        "blockers": blockers,
        "warnings": warnings,
        "skipped": skipped,
        "side_effect_safety": side_effect_safety,
    }


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Product Management Gray Smoke Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- mode: `{report['mode']}`",
        f"- include_fake_writes: `{report['include_fake_writes']}`",
        f"- old_write_endpoints_executed: `{report['side_effect_safety']['old_write_endpoints_executed']}`",
        f"- checkout_executed: `{report['side_effect_safety']['checkout_executed']}`",
        f"- payment_provider_called: `{report['side_effect_safety']['payment_provider_called']}`",
        f"- external_payment_executed: `{report['side_effect_safety']['external_payment_executed']}`",
        "",
        "## Summary",
        "",
        f"- route_results: {len(report['route_results'])}",
        f"- blockers: {len(report['blockers'])}",
        f"- warnings: {len(report['warnings'])}",
        f"- skipped: {len(report['skipped'])}",
        "",
        "## Routes",
        "",
        "| name | method | path | status_code | ok | side_effect_risk | issues |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for item in report["route_results"]:
        issue_text = "; ".join(issue["reason"] for issue in item["issues"]) or "-"
        lines.append(
            f"| {item['name']} | {item['method']} | `{item['path']}` | {item['status_code']} | {item['ok']} | {item['side_effect_risk']} | {issue_text} |"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- `{item.get('reason')}`: {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- `{item.get('reason')}`: {item}" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Skipped", ""])
    lines.extend([f"- `{item.get('reason')}`: {item.get('message', item)}" for item in report["skipped"]] or ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI-CRM Next Product Management gray-release preparation smoke checks.")
    parser.add_argument("--next-testclient", action="store_true", help="Run against AI-CRM Next FastAPI TestClient.")
    parser.add_argument("--next-base-url", default="", help="Run read-only checks against a Next HTTP base URL.")
    parser.add_argument("--include-fake-writes", action="store_true", help="Opt in to product write checks against Next TestClient fake/in-memory APIs only.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    print("old_write_endpoints_executed:", report["side_effect_safety"]["old_write_endpoints_executed"])
    print("checkout_executed:", report["side_effect_safety"]["checkout_executed"])
    print("payment_provider_called:", report["side_effect_safety"]["payment_provider_called"])
    print("external_payment_executed:", report["side_effect_safety"]["external_payment_executed"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
