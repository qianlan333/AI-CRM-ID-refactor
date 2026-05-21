#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicrm_next.commerce.parity_spec import ENDPOINT_SPECS, READ_ENDPOINTS, WRITE_ENDPOINTS, compare_endpoint_payloads, compare_status_code  # noqa: E402

OLD_WRITE_SKIP_REASON = "old_write_endpoint_disabled"
OLD_WRITE_SKIP_NOTE = "Use fixture mode or explicit allow flag; do not run writes against production old service."


def _load_fixture(fixture_dir: Path, endpoint_name: str) -> dict[str, Any]:
    data = json.loads((fixture_dir / f"{endpoint_name}.json").read_text(encoding="utf-8"))
    return data if "payload" in data else {"status_code": 200, "payload": data}


def _fetch_http(base_url: str, endpoint_name: str) -> dict[str, Any]:
    spec = ENDPOINT_SPECS[endpoint_name]
    with httpx.Client(timeout=10.0) as client:
        response = client.request(spec.method, base_url.rstrip("/") + spec.path, json=spec.body if spec.method == "POST" else None)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text}
    return {"status_code": response.status_code, "payload": payload}


def _fetch_next_testclient(endpoint_name: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    spec = ENDPOINT_SPECS[endpoint_name]
    response = TestClient(create_app()).request(spec.method, spec.path, json=spec.body if spec.method == "POST" else None)
    return {"status_code": response.status_code, "payload": response.json()}


def _endpoint_names(args: argparse.Namespace) -> list[str]:
    endpoints = list(READ_ENDPOINTS)
    if args.old_fixture_dir or getattr(args, "allow_old_write_endpoints", False):
        endpoints.extend(WRITE_ENDPOINTS)
    elif args.old_base_url:
        endpoints.extend(WRITE_ENDPOINTS)
    return endpoints


def _skipped_old_write_result(endpoint_name: str) -> dict[str, Any]:
    spec = ENDPOINT_SPECS[endpoint_name]
    return {
        "endpoint": endpoint_name,
        "method": spec.method,
        "path": spec.path,
        "old_status": "skipped",
        "next_status": "skipped",
        "status": "SKIPPED",
        "reason": OLD_WRITE_SKIP_REASON,
        "note": OLD_WRITE_SKIP_NOTE,
        "issues": [{"rule": OLD_WRITE_SKIP_REASON, "severity": "skip", "message": OLD_WRITE_SKIP_NOTE}],
    }


def run_compare(args: argparse.Namespace) -> dict[str, Any]:
    results = []
    old_write_endpoints_enabled = bool(args.old_base_url and getattr(args, "allow_old_write_endpoints", False))
    for endpoint_name in _endpoint_names(args):
        spec = ENDPOINT_SPECS[endpoint_name]
        if endpoint_name in WRITE_ENDPOINTS and args.old_base_url and not old_write_endpoints_enabled:
            results.append(_skipped_old_write_result(endpoint_name))
            continue
        old_result = _load_fixture(Path(args.old_fixture_dir), endpoint_name) if args.old_fixture_dir else _fetch_http(args.old_base_url, endpoint_name)
        next_result = _fetch_next_testclient(endpoint_name) if args.next_testclient else _fetch_http(args.next_base_url, endpoint_name)
        issues = compare_status_code(old_result["status_code"], next_result["status_code"], expected_status=spec.expected_status)
        issues.extend(compare_endpoint_payloads(endpoint_name, old_result["payload"], next_result["payload"]))
        results.append(
            {
                "endpoint": endpoint_name,
                "method": spec.method,
                "path": spec.path,
                "old_status": old_result["status_code"],
                "next_status": next_result["status_code"],
                "status": "PASS" if not any(issue.get("severity") == "fail" for issue in issues) else "FAIL",
                "issues": issues,
            }
        )
    return {
        "ok": not any(item["status"] == "FAIL" for item in results),
        "mode": {"old": "fixture" if args.old_fixture_dir else "http", "next": "testclient" if args.next_testclient else "http"},
        "side_effect_safety": {
            "old_write_endpoints_enabled": old_write_endpoints_enabled,
            "note": "Old HTTP mode defaults to read-only endpoints. Checkout endpoints are compared through fixtures or Next fake mode unless explicitly enabled.",
        },
        "results": results,
    }


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Commerce Parity Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- old mode: {report['mode']['old']}",
        f"- next mode: {report['mode']['next']}",
        f"- side-effect safety: {report['side_effect_safety']['note']}",
        f"- old_write_endpoints_enabled: {str(report['side_effect_safety']['old_write_endpoints_enabled']).lower()}",
        "",
        "| endpoint | method | path | old_status | next_status | status | issues |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["results"]:
        visible_issues = [issue for issue in item["issues"] if issue.get("severity") in {"fail", "skip"}]
        issue_text = "; ".join(issue.get("rule", "issue") for issue in visible_issues) or "-"
        lines.append(f"| {item['endpoint']} | {item['method']} | `{item['path']}` | {item['old_status']} | {item['next_status']} | {item['status']} | {issue_text} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare old Flask and AI-CRM Next commerce API parity.")
    parser.add_argument("--old-base-url", default="")
    parser.add_argument("--next-base-url", default="")
    parser.add_argument("--old-fixture-dir", default="")
    parser.add_argument("--next-testclient", action="store_true")
    parser.add_argument(
        "--allow-old-write-endpoints",
        action="store_true",
        help="DANGEROUS: allows checkout POST requests against --old-base-url. Never use with a production old service.",
    )
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.old_fixture_dir and not args.old_base_url:
        raise SystemExit("old-base-url or old-fixture-dir is required")
    if not args.next_testclient and not args.next_base_url:
        raise SystemExit("next-base-url or next-testclient is required")
    report = run_compare(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
