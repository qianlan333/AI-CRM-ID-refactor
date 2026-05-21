#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aicrm_next.automation_engine.parity_spec import DEFAULT_SAFE_ENDPOINTS, ENDPOINT_SPECS, compare_endpoint_payloads, compare_status_code  # noqa: E402

Json = dict[str, Any]


def _load_fixture(fixture_dir: Path, endpoint_name: str) -> Json:
    data = json.loads((fixture_dir / f"{endpoint_name}.json").read_text(encoding="utf-8"))
    return data if "payload" in data else {"status_code": 200, "payload": data}


def _fetch_http(base_url: str, endpoint_name: str) -> Json:
    spec = ENDPOINT_SPECS[endpoint_name]
    with httpx.Client(timeout=10.0) as client:
        response = client.request(spec.method, base_url.rstrip("/") + spec.path, json=spec.body if spec.method == "POST" else None)
    try:
        payload: Json | str = response.json()
    except ValueError:
        payload = response.text
    return {"status_code": response.status_code, "payload": payload}


def _fetch_next_testclient(endpoint_name: str) -> Json:
    from fastapi.testclient import TestClient

    from aicrm_next.automation_engine.repo import reset_automation_fixture_state
    from aicrm_next.main import create_app

    reset_automation_fixture_state()
    spec = ENDPOINT_SPECS[endpoint_name]
    response = TestClient(create_app()).request(spec.method, spec.path, json=spec.body if spec.method == "POST" else None)
    return {"status_code": response.status_code, "payload": response.json()}


def run_compare(args: argparse.Namespace) -> Json:
    results: list[Json] = []
    for endpoint_name in DEFAULT_SAFE_ENDPOINTS:
        spec = ENDPOINT_SPECS[endpoint_name]
        old_result = _load_fixture(Path(args.old_fixture_dir), endpoint_name) if args.old_fixture_dir else _fetch_http(args.old_base_url, endpoint_name)
        next_result = _fetch_next_testclient(endpoint_name) if args.next_testclient else _fetch_http(args.next_base_url, endpoint_name)
        issues = compare_status_code(old_result["status_code"], next_result["status_code"], expected_status=spec.expected_status)
        if isinstance(old_result["payload"], dict) and isinstance(next_result["payload"], dict):
            issues.extend(compare_endpoint_payloads(endpoint_name, old_result["payload"], next_result["payload"]))
        else:
            issues.append({"rule": "payload_not_object", "severity": "fail"})
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
            "old_write_endpoints_executed": False,
            "real_automation_write_executed": False,
            "real_activation_webhook_executed": False,
            "real_openclaw_push_executed": False,
            "real_workflow_runtime_executed": False,
            "real_agent_runtime_executed": False,
            "real_external_webhook_executed": False,
            "note": "Automation parity uses old fixtures and Next fake/stub endpoints; no old write endpoint is called.",
        },
        "results": results,
    }


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Automation Conversion Parity Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- old mode: {report['mode']['old']}",
        f"- next mode: {report['mode']['next']}",
        f"- side-effect safety: {report['side_effect_safety']['note']}",
        "",
        "| endpoint | method | path | old_status | next_status | status | issues |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["results"]:
        issues = "; ".join(issue.get("rule", "issue") for issue in item["issues"] if issue.get("severity") == "fail") or "-"
        lines.append(f"| {item['endpoint']} | {item['method']} | `{item['path']}` | {item['old_status']} | {item['next_status']} | {item['status']} | {issues} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare old automation fixtures and AI-CRM Next automation API parity.")
    parser.add_argument("--old-base-url", default="")
    parser.add_argument("--next-base-url", default="")
    parser.add_argument("--old-fixture-dir", default="")
    parser.add_argument("--next-testclient", action="store_true")
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
