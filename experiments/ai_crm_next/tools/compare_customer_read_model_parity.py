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

from aicrm_next.customer_read_model.parity_spec import (  # noqa: E402
    ENDPOINT_SPECS,
    compare_endpoint_payloads,
    compare_status_code,
)


def _load_fixture(fixture_dir: Path, endpoint_name: str) -> dict[str, Any]:
    path = fixture_dir / f"{endpoint_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing old fixture: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "payload" not in data:
        return {"status_code": 200, "payload": data}
    return data


def _fetch_http(base_url: str, endpoint_name: str) -> dict[str, Any]:
    spec = ENDPOINT_SPECS[endpoint_name]
    with httpx.Client(timeout=10.0) as client:
        response = client.request(spec.method, base_url.rstrip("/") + spec.path)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text}
    return {"status_code": response.status_code, "payload": payload}


def _fetch_next_testclient(endpoint_name: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    spec = ENDPOINT_SPECS[endpoint_name]
    response = TestClient(create_app()).request(spec.method, spec.path)
    return {"status_code": response.status_code, "payload": response.json()}


def run_compare(args: argparse.Namespace) -> dict[str, Any]:
    results = []
    for endpoint_name, spec in ENDPOINT_SPECS.items():
        if args.old_fixture_dir:
            old_result = _load_fixture(Path(args.old_fixture_dir), endpoint_name)
        elif args.old_base_url:
            old_result = _fetch_http(args.old_base_url, endpoint_name)
        else:
            raise ValueError("old-base-url or old-fixture-dir is required")

        if args.next_testclient:
            next_result = _fetch_next_testclient(endpoint_name)
        elif args.next_base_url:
            next_result = _fetch_http(args.next_base_url, endpoint_name)
        else:
            raise ValueError("next-base-url or next-testclient is required")

        issues = []
        issues.extend(
            compare_status_code(
                int(old_result["status_code"]),
                int(next_result["status_code"]),
                expected_status=spec.expected_status,
            )
        )
        if isinstance(old_result.get("payload"), dict) and isinstance(next_result.get("payload"), dict):
            issues.extend(compare_endpoint_payloads(endpoint_name, old_result["payload"], next_result["payload"]))
        else:
            issues.append({"rule": "payload_type", "severity": "fail", "message": "payload is not a JSON object"})
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
        "mode": {
            "old": "fixture" if args.old_fixture_dir else "http",
            "next": "testclient" if args.next_testclient else "http",
        },
        "side_effect_safety": {
            "note": "Customer Read Model parity uses read-only endpoints only.",
        },
        "results": results,
    }


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Customer Read Model Parity Report",
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
        fail_issues = [issue for issue in item["issues"] if issue.get("severity") == "fail"]
        issue_text = "; ".join(issue.get("rule", "issue") for issue in fail_issues) or "-"
        lines.append(
            f"| {item['endpoint']} | {item['method']} | `{item['path']}` | {item['old_status']} | "
            f"{item['next_status']} | {item['status']} | {issue_text} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare old Flask and AI-CRM Next Customer Read Model API parity.")
    parser.add_argument("--old-base-url", default="", help="Old Flask AI-CRM base URL. Used only through HTTP.")
    parser.add_argument("--next-base-url", default="", help="AI-CRM Next base URL. Used only through HTTP.")
    parser.add_argument("--old-fixture-dir", default="", help="Directory containing old customer read model JSON response fixtures.")
    parser.add_argument("--next-testclient", action="store_true", help="Use AI-CRM Next FastAPI TestClient instead of HTTP.")
    parser.add_argument("--output-md", required=True, help="Markdown report output path.")
    parser.add_argument("--output-json", required=True, help="JSON report output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_compare(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
