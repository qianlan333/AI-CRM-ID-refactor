#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGET_ROUTE = "/admin/customers"
TARGET_PROBE_PATH = "/admin/customers?keyword=phase3f"
EXPECTED_ENDPOINT_MODULE = "aicrm_next.frontend_compat.legacy_routes"
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FIXTURE_MARKERS = ("fixture", "local_contract", "demo", "local_contract_customer")
PRODUCTION_PROBE_DATABASE_URL = (
    "postgresql://admincustomers:admincustomers@127.0.0.1:1/aicrm_admin_customers_phase3f_probe"
)
FORBIDDEN_HANDLER_CALLS = (
    "list_customers_via_legacy",
    "get_customer_via_legacy",
    "get_timeline_via_legacy",
    "recent_messages_via_legacy",
    "production_data_ready",
)
REQUIRED_HANDLER_MARKERS = ("ListCustomersQuery", "ListCustomersRequest")
FRONTEND_SQL_PATTERNS = (
    re.compile(r"\bSELECT\b.*\bFROM\b", re.I),
    re.compile(r"\bINSERT\s+INTO\b", re.I),
    re.compile(r"\bUPDATE\s+[a-zA-Z_][\w.]*\s+SET\b", re.I),
    re.compile(r"\bDELETE\s+FROM\b", re.I),
    re.compile(r"\bdb\.session\b", re.I),
    re.compile(r"\bengine\.execute\b", re.I),
    re.compile(r"\btext\s*\(", re.I),
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contains_fixture_marker(value: str | bytes | dict[str, Any] | list[Any]) -> bool:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    lower = text.lower()
    return any(marker in lower for marker in FIXTURE_MARKERS)


@contextmanager
def production_admin_customers_probe_env():
    keys = {
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get(
            "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"
        ),
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": os.environ.get(
            "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"
        ),
        "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC": os.environ.get(
            "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC"
        ),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
    }
    os.environ["AICRM_NEXT_ENV"] = "production"
    os.environ["DATABASE_URL"] = PRODUCTION_PROBE_DATABASE_URL
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ.pop("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", None)
    os.environ.pop("AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC", None)
    os.environ.setdefault("SECRET_KEY", "phase3f-admin-customers-shell")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "phase3f-admin-customers-shell")
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _make_client():
    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"fastapi dependency unavailable: {exc}") from exc

    module = importlib.import_module("aicrm_next.main")
    return TestClient(module.create_app())


def _match_name(match: Any) -> str:
    return getattr(match, "name", str(match)).upper()


def first_matching_endpoint_module(app: Any, *, method: str, path: str) -> str:
    scope = {
        "type": "http",
        "method": method.upper(),
        "path": path,
        "root_path": "",
        "headers": [],
    }
    for route in getattr(app, "routes", []):
        matches = getattr(route, "matches", None)
        if not callable(matches):
            continue
        match, _ = route.matches(scope)
        if _match_name(match) != "FULL":
            continue
        endpoint = getattr(route, "endpoint", None)
        return getattr(endpoint, "__module__", "") if endpoint else ""
    return ""


def matching_route_methods(app: Any, *, route_path: str, endpoint_module: str) -> set[str]:
    methods: set[str] = set()
    for route in getattr(app, "routes", []):
        endpoint = getattr(route, "endpoint", None)
        if getattr(endpoint, "__module__", "") != endpoint_module:
            continue
        if getattr(route, "path", "") != route_path:
            continue
        methods.update(str(method).upper() for method in getattr(route, "methods", set()) or set())
    return methods


def check_exact_route_owner(app: Any) -> dict[str, Any]:
    blockers: list[str] = []
    actual_module = first_matching_endpoint_module(app, method="GET", path=TARGET_ROUTE)
    if actual_module != EXPECTED_ENDPOINT_MODULE:
        blockers.append(
            f"{TARGET_ROUTE} resolved to {actual_module or 'no endpoint'}, expected {EXPECTED_ENDPOINT_MODULE}"
        )
    if actual_module in {
        "aicrm_next.production_compat.api",
        "aicrm_next.integration_gateway.legacy_flask_facade",
    }:
        blockers.append(f"{TARGET_ROUTE} is shadowed by compatibility facade endpoint {actual_module}")

    methods = matching_route_methods(
        app,
        route_path=TARGET_ROUTE,
        endpoint_module=EXPECTED_ENDPOINT_MODULE,
    )
    state_methods = sorted(methods & STATE_CHANGING_METHODS)
    if state_methods:
        blockers.append(f"{TARGET_ROUTE} exposes state-changing methods: {', '.join(state_methods)}")
    return {
        "ok": not blockers,
        "blockers": blockers,
        "route": {
            "path": TARGET_ROUTE,
            "expected_module": EXPECTED_ENDPOINT_MODULE,
            "actual_module": actual_module,
            "methods": sorted(methods),
        },
    }


def check_response_headers(client: Any) -> dict[str, Any]:
    response = client.get(TARGET_PROBE_PATH)
    record = {
        "path": TARGET_PROBE_PATH,
        "status_code": response.status_code,
        "route_owner_header": response.headers.get("X-AICRM-Route-Owner", ""),
        "compatibility_facade": response.headers.get("X-AICRM-Compatibility-Facade", ""),
    }
    blockers: list[str] = []
    if record["route_owner_header"] != "ai_crm_next":
        blockers.append(f"{TARGET_ROUTE} missing X-AICRM-Route-Owner=ai_crm_next")
    if record["compatibility_facade"] == "legacy_flask_facade":
        blockers.append(f"{TARGET_ROUTE} returned legacy_flask_facade compatibility header")
    return {"ok": not blockers, "blockers": blockers, "probe": record}


def check_production_unavailable_behavior(client: Any) -> dict[str, Any]:
    response = client.get(TARGET_PROBE_PATH)
    body_text = response.text
    record = {
        "path": TARGET_PROBE_PATH,
        "status_code": response.status_code,
        "fixture_marker_present": _contains_fixture_marker(body_text),
        "contains_page_error_text": (
            "生产" in body_text
            or "page_error" in body_text
            or "读取失败" in body_text
            or "admin-alert--error" in body_text
            or "connection failed" in body_text
        ),
        "contains_customer_page": "客户列表" in body_text and "客户查找" in body_text,
        "compatibility_facade": response.headers.get("X-AICRM-Compatibility-Facade", ""),
    }
    blockers: list[str] = []
    if response.status_code >= 500:
        blockers.append(f"{TARGET_ROUTE} returned {response.status_code} in production probe")
    if response.status_code == 200 and record["fixture_marker_present"]:
        blockers.append(f"{TARGET_ROUTE} rendered fixture/local_contract/demo customer data in production probe")
    if record["compatibility_facade"] == "legacy_flask_facade":
        blockers.append(f"{TARGET_ROUTE} returned route-level legacy_flask_facade header")
    if response.status_code == 200 and not record["contains_customer_page"]:
        blockers.append(f"{TARGET_ROUTE} did not render the customer list shell")
    if response.status_code == 200 and not record["contains_page_error_text"]:
        blockers.append(f"{TARGET_ROUTE} rendered 200 production probe without degraded/page_error text")
    return {"ok": not blockers, "blockers": blockers, "probe": record}


def _function_source(source: str, function_name: str) -> str:
    lines = source.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith(f"def {function_name}(") or line.startswith(f"async def {function_name}("):
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith((" ", "\t", "@")) and (
            line.startswith("def ") or line.startswith("async def ") or line.startswith("class ")
        ):
            end = index
            break
    return "\n".join(lines[start:end])


def check_static_boundaries() -> dict[str, Any]:
    blockers: list[str] = []
    legacy_routes = ROOT / "aicrm_next/frontend_compat/legacy_routes.py"
    source = _read(legacy_routes)
    handler_source = _function_source(source, "admin_customers")
    if not handler_source:
        blockers.append(f"{_rel(legacy_routes)} missing admin_customers handler")
    else:
        for forbidden in FORBIDDEN_HANDLER_CALLS:
            if forbidden in handler_source:
                blockers.append(f"{_rel(legacy_routes)} admin_customers directly calls {forbidden}")
        for required in REQUIRED_HANDLER_MARKERS:
            if required not in handler_source:
                blockers.append(f"{_rel(legacy_routes)} admin_customers must call {required}")

    if "from aicrm_next.integration_gateway.legacy_customer_read_facade import list_customers_via_legacy" in source:
        blockers.append(f"{_rel(legacy_routes)} retains unused direct list_customers_via_legacy import")

    for lineno, line in enumerate(source.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for pattern in FRONTEND_SQL_PATTERNS:
            if pattern.search(line):
                blockers.append(f"{_rel(legacy_routes)}:{lineno} contains direct SQL token")

    if "@router.get(\"/admin/customers\"" not in source:
        blockers.append(f"{_rel(legacy_routes)} missing GET /admin/customers route")
    for method in ("post", "put", "patch", "delete"):
        if f"@router.{method}(\"/admin/customers\"" in source:
            blockers.append(f"{_rel(legacy_routes)} adds {method.upper()} /admin/customers")

    try:
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "origin/main",
                "--",
                "aicrm_next/main.py",
                "aicrm_next/production_compat/api.py",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for path in [line.strip() for line in diff.stdout.splitlines() if line.strip()]:
            blockers.append(f"{path} must not be modified by Phase 3F")
    except Exception as exc:
        blockers.append(f"could not compare protected runtime files against origin/main: {exc}")

    combined = "\n".join(
        _read(path)
        for path in (
            legacy_routes,
            ROOT / "aicrm_next/customer_read_model/application.py",
            ROOT / "docs/development/phase_3f_admin_customers_shell_hardening.md",
        )
        if path.exists()
    )
    for marker in (
        "WECHAT_REAL_CALL",
        "WECOM_REAL_CALL",
        "PAYMENT_REAL_CALL",
        "OPENCLAW_REAL_CALL",
        "MCP_REAL_CALL",
        "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC=1",
        "real_allowed",
        "real_enabled",
    ):
        if marker in combined:
            blockers.append(f"Phase 3F artifacts must not enable real external calls marker={marker}")

    return {"ok": not blockers, "blockers": blockers}


def run_fastapi_probes() -> dict[str, Any]:
    try:
        with production_admin_customers_probe_env():
            client = _make_client()
            checks = {
                "exact_route_owner": check_exact_route_owner(client.app),
                "response_headers": check_response_headers(client),
                "production_unavailable_behavior": check_production_unavailable_behavior(client),
            }
    except Exception as exc:
        return {
            "ok": False,
            "blockers": [f"fastapi_testclient_probe_unavailable: {exc}"],
            "checks": {},
        }
    blockers: list[str] = []
    for check in checks.values():
        blockers.extend(check.get("blockers", []))
    return {"ok": not blockers, "blockers": blockers, "checks": checks}


def build_report() -> dict[str, Any]:
    static = check_static_boundaries()
    fastapi = run_fastapi_probes()
    blockers = list(static.get("blockers", [])) + list(fastapi.get("blockers", []))
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "target_route": {
            "method": "GET",
            "route": TARGET_ROUTE,
            "probe_path": TARGET_PROBE_PATH,
            "expected_endpoint_module": EXPECTED_ENDPOINT_MODULE,
        },
        "blockers": blockers,
        "static": static,
        "fastapi_probes": fastapi,
    }


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 3F Admin Customers Shell Check",
        "",
        f"- overall: {report['overall']}",
        f"- route: GET {TARGET_ROUTE}",
        f"- blockers: {len(report.get('blockers', []))}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers", [])
    lines.extend([f"- {item}" for item in blockers] if blockers else ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args(argv)

    report = build_report()
    if args.output_json:
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output_md:
        write_markdown_report(report, args.output_md)
    print(f"overall: {report['overall']}")
    if report.get("blockers"):
        print("blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
