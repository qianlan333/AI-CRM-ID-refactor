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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


DEFAULT_READ_ENDPOINTS: tuple[SmokeEndpoint, ...] = (
    SmokeEndpoint("image_page", "GET", "/admin/image-library", route_type="page", required_keys=()),
    SmokeEndpoint("image_list", "GET", "/api/admin/image-library", required_keys=("ok", "items", "total", "limit", "offset")),
    SmokeEndpoint("attachment_page", "GET", "/admin/attachment-library", route_type="page", required_keys=()),
    SmokeEndpoint("attachment_list", "GET", "/api/admin/attachment-library", required_keys=("ok", "items", "total", "limit", "offset")),
    SmokeEndpoint("miniprogram_page", "GET", "/admin/miniprogram-library", route_type="page", required_keys=()),
    SmokeEndpoint("miniprogram_list", "GET", "/api/admin/miniprogram-library", required_keys=("ok", "items", "total", "limit", "offset")),
)


@dataclass(frozen=True)
class FakeWriteScenario:
    name: str
    create_path: str
    update_path_template: str
    delete_path_template: str
    create_payload: Json
    update_patch: Json
    id_path: str = "item.id"


FAKE_WRITE_SCENARIOS: tuple[FakeWriteScenario, ...] = (
    FakeWriteScenario(
        name="image",
        create_path="/api/admin/image-library",
        update_path_template="/api/admin/image-library/{id}",
        delete_path_template="/api/admin/image-library/{id}",
        create_payload={
            "name": "灰度图片 fixture",
            "file_name": "gray-image.png",
            "content_type": "image/png",
            "file_size": 8,
            "width": 1,
            "height": 1,
            "data_url": "data:image/png;base64,ZmFrZQ==",
            "tags": ["gray-smoke"],
        },
        update_patch={"name": "灰度图片 fixture 更新"},
    ),
    FakeWriteScenario(
        name="attachment",
        create_path="/api/admin/attachment-library",
        update_path_template="/api/admin/attachment-library/{id}",
        delete_path_template="/api/admin/attachment-library/{id}",
        create_payload={
            "name": "灰度附件 fixture",
            "file_name": "gray.pdf",
            "mime_type": "application/pdf",
            "file_size": 10,
            "data_base64": "ZmFrZQ==",
            "tags": ["gray-smoke"],
            "enabled": True,
        },
        update_patch={"enabled": False},
    ),
    FakeWriteScenario(
        name="miniprogram",
        create_path="/api/admin/miniprogram-library",
        update_path_template="/api/admin/miniprogram-library/{id}",
        delete_path_template="/api/admin/miniprogram-library/{id}",
        create_payload={
            "title": "灰度小程序 fixture",
            "appid": "appid_masked_gray",
            "page_path": "pages/gray/index",
            "thumb_image_id": "image_masked_001",
            "description": "gray smoke fixture",
            "tags": ["gray-smoke"],
            "enabled": True,
        },
        update_patch={"enabled": False},
    ),
)


def _build_testclient():
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    return TestClient(create_app())


def _reset_media_state() -> None:
    from aicrm_next.media_library.repo import reset_media_library_fixture_state

    reset_media_library_fixture_state()


def _request_testclient(client: Any, method: str, path: str, payload: Json | None = None) -> tuple[int, Json | str]:
    response = client.request(method, path, json=payload)
    try:
        body: Json | str = response.json()
    except Exception:
        body = response.text
    return response.status_code, body


def _request_http(base_url: str, method: str, path: str) -> tuple[int, Json | str]:
    if method != "GET":
        raise RuntimeError("HTTP mode only supports GET for Media Library gray smoke.")
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


def _run_read_endpoint(args: argparse.Namespace, client: Any | None, endpoint: SmokeEndpoint) -> Json:
    if args.next_testclient:
        status_code, payload = _request_testclient(client, endpoint.method, endpoint.path)
    else:
        status_code, payload = _request_http(args.next_base_url, endpoint.method, endpoint.path)
    return _result(
        name=endpoint.name,
        method=endpoint.method,
        path=endpoint.path,
        status_code=status_code,
        expected_status=endpoint.expected_status,
        payload=payload,
        required_keys=endpoint.required_keys,
        route_type=endpoint.route_type,
        side_effect_risk=endpoint.side_effect_risk,
    )


def _extract_item(payload: Json | str) -> Json:
    if not isinstance(payload, dict) or not isinstance(payload.get("item"), dict):
        raise RuntimeError("fake write response missing item")
    return payload["item"]


def _run_fake_write_scenario(client: Any, scenario: FakeWriteScenario) -> list[Json]:
    results: list[Json] = []
    create_status, create_payload = _request_testclient(client, "POST", scenario.create_path, scenario.create_payload)
    results.append(
        _result(
            name=f"{scenario.name}_create_fake_write",
            method="POST",
            path=scenario.create_path,
            status_code=create_status,
            expected_status=200,
            payload=create_payload,
            required_keys=("ok", "item"),
            side_effect_risk="next_fake_write",
        )
    )
    item = _extract_item(create_payload)
    item_id = item["id"]
    update_payload = {**item, **scenario.update_patch}
    update_path = scenario.update_path_template.format(id=item_id)
    update_status, update_body = _request_testclient(client, "PUT", update_path, update_payload)
    results.append(
        _result(
            name=f"{scenario.name}_update_fake_write",
            method="PUT",
            path=update_path,
            status_code=update_status,
            expected_status=200,
            payload=update_body,
            required_keys=("ok", "item"),
            side_effect_risk="next_fake_write",
        )
    )
    delete_path = scenario.delete_path_template.format(id=item_id)
    delete_status, delete_body = _request_testclient(client, "DELETE", delete_path)
    results.append(
        _result(
            name=f"{scenario.name}_delete_fake_write",
            method="DELETE",
            path=delete_path,
            status_code=delete_status,
            expected_status=200,
            payload=delete_body,
            required_keys=("ok",),
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
        "external_upload_executed": False,
        "wecom_media_upload_executed": False,
        "default_endpoints_get_only": all(endpoint.method == "GET" for endpoint in DEFAULT_READ_ENDPOINTS),
        "fake_writes_next_testclient_only": True,
    }

    if not args.next_testclient and not args.next_base_url:
        blockers.append({"reason": "missing_next_target", "message": "Use --next-testclient or --next-base-url."})
        return _report(args, route_results, blockers, warnings, skipped, side_effect_safety)
    if args.include_fake_writes and not args.next_testclient:
        blockers.append({"reason": "fake_writes_require_next_testclient", "message": "--include-fake-writes is allowed only with --next-testclient."})
        return _report(args, route_results, blockers, warnings, skipped, side_effect_safety)

    client = None
    if args.next_testclient:
        _reset_media_state()
        client = _build_testclient()

    for endpoint in DEFAULT_READ_ENDPOINTS:
        result = _run_read_endpoint(args, client, endpoint)
        route_results.append(result)
        blockers.extend(result["issues"])

    if args.include_fake_writes:
        for scenario in FAKE_WRITE_SCENARIOS:
            try:
                scenario_results = _run_fake_write_scenario(client, scenario)
            except Exception as exc:
                blockers.append({"reason": "fake_write_exception", "scenario": scenario.name, "message": str(exc)})
                continue
            route_results.extend(scenario_results)
            for result in scenario_results:
                blockers.extend(result["issues"])
    else:
        skipped.append({"reason": "fake_writes_not_requested", "message": "POST/PUT/DELETE checks require --include-fake-writes and target Next TestClient only."})

    if args.next_testclient:
        _reset_media_state()

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
        "# Media Library Gray Smoke Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- mode: `{report['mode']}`",
        f"- include_fake_writes: `{report['include_fake_writes']}`",
        f"- old_write_endpoints_executed: `{report['side_effect_safety']['old_write_endpoints_executed']}`",
        f"- external_upload_executed: `{report['side_effect_safety']['external_upload_executed']}`",
        f"- wecom_media_upload_executed: `{report['side_effect_safety']['wecom_media_upload_executed']}`",
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
    parser = argparse.ArgumentParser(description="Run AI-CRM Next Media Library gray-release preparation smoke checks.")
    parser.add_argument("--next-testclient", action="store_true", help="Run against AI-CRM Next FastAPI TestClient.")
    parser.add_argument("--next-base-url", default="", help="Run read-only checks against a Next HTTP base URL.")
    parser.add_argument("--include-fake-writes", action="store_true", help="Opt in to POST/PUT/DELETE checks against Next TestClient fake/in-memory media APIs only.")
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
    print("external_upload_executed:", report["side_effect_safety"]["external_upload_executed"])
    print("wecom_media_upload_executed:", report["side_effect_safety"]["wecom_media_upload_executed"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
