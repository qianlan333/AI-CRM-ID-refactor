#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

Json = dict[str, Any]


FORBIDDEN_PLACEHOLDER_TEXT = [
    "New UI",
    "redesign",
    "TODO replace old frontend",
    "experimental replacement UI",
    "new dashboard placeholder",
]


@dataclass(frozen=True)
class FrontendRouteSpec:
    route: str
    expected_status: int
    frontend_source: str
    parity_status: str
    must_contain_text: tuple[str, ...]
    must_not_contain_text: tuple[str, ...] = tuple(FORBIDDEN_PLACEHOLDER_TEXT)
    screenshot_required: bool = True
    notes: str = ""


FRONTEND_ROUTES: tuple[FrontendRouteSpec, ...] = (
    FrontendRouteSpec(
        "/admin",
        200,
        "copied legacy admin shell via frontend_compat",
        "partial adapter",
        ("后台", "客户", "问卷"),
        notes="Dashboard shell baseline; not production auth.",
    ),
    FrontendRouteSpec(
        "/admin/customers",
        200,
        "copied admin_console/customers.html",
        "partial adapter",
        ("客户", "筛选", "负责人"),
        notes="Fixture customer list; old test DB samples are separate dual-run coverage.",
    ),
    FrontendRouteSpec(
        "/admin/user-ops/ui",
        200,
        "copied admin_user_ops.html",
        "parity-ready partial",
        ("引流品总数", "已加微", "未加微", "黄小璨已激活", "黄小璨未激活", "发送记录"),
        notes="Legacy User Ops workspace with fixture-backed API adapters.",
    ),
    FrontendRouteSpec(
        "/admin/questionnaires",
        200,
        "copied admin_console/questionnaires.html",
        "partial adapter",
        ("问卷", "创建", "编辑"),
        notes="Admin questionnaire list/editor baseline.",
    ),
    FrontendRouteSpec(
        "/admin/questionnaires/ui",
        200,
        "copied admin_console/questionnaires.html",
        "partial adapter",
        ("问卷", "创建", "编辑"),
        notes="Alias kept for old entry compatibility.",
    ),
    FrontendRouteSpec(
        "/admin/automation-conversion",
        200,
        "copied admin_console/automation_program_list.html",
        "partial adapter",
        ("自动化转化", "方案", "默认转化方案"),
        notes="Program list entry baseline; workspaces remain partial.",
    ),
    FrontendRouteSpec(
        "/admin/wechat-pay/products",
        200,
        "legacy admin shell partial adapter",
        "partial adapter",
        ("商品", "价格", "enable / disable"),
        notes="Product management contract surfaced through partial shell.",
    ),
    FrontendRouteSpec(
        "/admin/wechat-pay/transactions",
        200,
        "copied admin_console/wechat_pay_transactions.html",
        "partial adapter",
        ("微信支付", "交易", "订单"),
        notes="Fake payment transaction data only.",
    ),
    FrontendRouteSpec(
        "/admin/alipay/transactions",
        200,
        "legacy admin shell partial adapter",
        "partial adapter",
        ("支付宝", "交易", "fake"),
        notes="Fake Alipay transaction contract; exact old page still partial.",
    ),
    FrontendRouteSpec(
        "/admin/image-library",
        200,
        "copied admin_console/image_library.html",
        "partial adapter",
        ("图片", "素材", "上传"),
        notes="Fixture media only; no cloud or WeCom upload.",
    ),
    FrontendRouteSpec(
        "/admin/attachment-library",
        200,
        "legacy admin shell partial adapter",
        "partial adapter",
        ("附件", "素材", "创建"),
        notes="Attachment page is partial shell until exact old template is available.",
    ),
    FrontendRouteSpec(
        "/admin/miniprogram-library",
        200,
        "copied admin_console/miniprogram_library.html",
        "partial adapter",
        ("小程序", "素材", "appid"),
        notes="Fixture mini-program materials only.",
    ),
    FrontendRouteSpec(
        "/s/hxc-activation-v1",
        200,
        "copied questionnaire_h5_page.html",
        "partial adapter",
        ("问卷", "提交"),
        notes="Public H5 questionnaire fixture; fake identity/OAuth only.",
    ),
    FrontendRouteSpec(
        "/p/course-masked-001",
        200,
        "simple public product contract page",
        "partial adapter",
        ("商品", "购买"),
        notes="Uses current fixture page_slug course-masked-001; no real payment.",
    ),
)


def _slugify_route(route: str) -> str:
    text = route.strip("/") or "admin-root"
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text or "route"


def _fetch_testclient(route: str) -> tuple[int, str]:
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    response = TestClient(create_app()).get(route)
    return response.status_code, response.text


def _fetch_http(base_url: str, route: str) -> tuple[int, str]:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(base_url.rstrip("/") + route)
    return response.status_code, response.text


def _capture_png_with_playwright(*, html: str, url: str, output_path: Path, mode: str) -> tuple[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on optional local package
        return "skipped", f"playwright unavailable: {exc}"

    try:  # pragma: no cover - browser availability is environment-dependent
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            if mode == "http":
                page.goto(url, wait_until="networkidle")
            else:
                page.set_content(html, wait_until="networkidle")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output_path), full_page=True)
            browser.close()
        return "generated", ""
    except Exception as exc:
        return "skipped", f"playwright browser unavailable: {exc}"


def run_capture(args: argparse.Namespace) -> Json:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    html_dir = output_dir / "html"
    png_dir = output_dir / "png"
    html_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    route_results: list[Json] = []
    for spec in FRONTEND_ROUTES:
        if args.mode == "testclient":
            status_code, html = _fetch_testclient(spec.route)
            route_url = spec.route
        else:
            status_code, html = _fetch_http(args.base_url, spec.route)
            route_url = args.base_url.rstrip("/") + spec.route

        slug = _slugify_route(spec.route)
        html_path = html_dir / f"{slug}.html"
        png_path = png_dir / f"{slug}.png"
        html_path.write_text(html, encoding="utf-8")

        missing_text = [token for token in spec.must_contain_text if token not in html]
        forbidden_text = [token for token in spec.must_not_contain_text if token in html]
        screenshot_status = "not_required"
        screenshot_reason = ""
        screenshot_path = ""
        if spec.screenshot_required:
            screenshot_status, screenshot_reason = _capture_png_with_playwright(
                html=html,
                url=route_url,
                output_path=png_path,
                mode=args.mode,
            )
            screenshot_path = str(png_path) if screenshot_status == "generated" else ""

        route_ok = status_code == spec.expected_status and not missing_text and not forbidden_text
        route_results.append(
            {
                **asdict(spec),
                "must_contain_text": list(spec.must_contain_text),
                "must_not_contain_text": list(spec.must_not_contain_text),
                "status_code": status_code,
                "ok": route_ok,
                "missing_required_text": missing_text,
                "forbidden_text_found": forbidden_text,
                "html_snapshot_path": str(html_path),
                "screenshot_status": screenshot_status,
                "screenshot_path": screenshot_path,
                "screenshot_reason": screenshot_reason,
            }
        )

    manifest_path = output_dir / "manifest.json"
    status_path = output_dir / "route_status.json"
    run_time = datetime.now(timezone.utc).isoformat()
    summary = {
        "routes": len(route_results),
        "passed": sum(1 for item in route_results if item["ok"]),
        "failed": sum(1 for item in route_results if not item["ok"]),
        "screenshots_generated": sum(1 for item in route_results if item["screenshot_status"] == "generated"),
        "screenshots_skipped": sum(1 for item in route_results if item["screenshot_status"] == "skipped"),
    }
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": run_time,
                "mode": args.mode,
                "base_url": args.base_url if args.mode == "http" else "",
                "route_count": summary["routes"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "screenshots_generated": summary["screenshots_generated"],
                "screenshots_skipped": summary["screenshots_skipped"],
                "routes": [asdict(spec) for spec in FRONTEND_ROUTES],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "ok": all(item["ok"] for item in route_results),
        "mode": args.mode,
        "base_url": args.base_url if args.mode == "http" else "",
        "run_time": run_time,
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "route_status_path": str(status_path),
        "summary": summary,
        "route_results": route_results,
    }
    status_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI-CRM Next Frontend Route Smoke Report",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- mode: `{report['mode']}`",
        f"- run_time: `{report['run_time']}`",
        f"- output_dir: `{report['output_dir']}`",
        f"- manifest: `{report['manifest_path']}`",
        f"- route_status: `{report['route_status_path']}`",
        "",
        "## Summary",
        "",
        f"- routes: {report['summary']['routes']}",
        f"- passed: {report['summary']['passed']}",
        f"- failed: {report['summary']['failed']}",
        f"- screenshots_generated: {report['summary']['screenshots_generated']}",
        f"- screenshots_skipped: {report['summary']['screenshots_skipped']}",
        "",
        "## Routes",
        "",
        "| route | status_code | ok | screenshot | html_snapshot | notes |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for item in report["route_results"]:
        issue_notes: list[str] = []
        if item["missing_required_text"]:
            issue_notes.append("missing=" + ",".join(item["missing_required_text"]))
        if item["forbidden_text_found"]:
            issue_notes.append("forbidden=" + ",".join(item["forbidden_text_found"]))
        if item["screenshot_status"] == "skipped":
            issue_notes.append(item["screenshot_reason"])
        if item["notes"]:
            issue_notes.append(item["notes"])
        lines.append(
            f"| `{item['route']}` | {item['status_code']} | {item['ok']} | "
            f"{item['screenshot_status']} | `{item['html_snapshot_path']}` | {'; '.join(issue_notes) or '-'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture AI-CRM Next frontend route smoke snapshots.")
    parser.add_argument("--output-dir", required=True, help="Artifact directory for manifest, route status, HTML, and optional PNGs.")
    parser.add_argument("--mode", choices=["testclient", "http"], default="testclient", help="Fetch routes with TestClient or HTTP.")
    parser.add_argument("--base-url", default="", help="Base URL for --mode http.")
    parser.add_argument("--output-md", default="/tmp/aicrm_next_frontend_route_smoke.md", help="Markdown report path.")
    parser.add_argument("--output-json", default="/tmp/aicrm_next_frontend_route_smoke.json", help="JSON report path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "http" and not args.base_url:
        raise SystemExit("--base-url is required when --mode http")
    report = run_capture(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print(f"wrote route status: {report['route_status_path']}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    if report["summary"]["screenshots_skipped"]:
        print("screenshots skipped:", report["summary"]["screenshots_skipped"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
