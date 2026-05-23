#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGET_ROUTES = {
    "/api/admin/customers/profile": "aicrm_next.customer_read_model.api",
    "/api/admin/customers/profile/tags": "aicrm_next.customer_read_model.api",
}
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FIXTURE_MARKERS = ("fixture", "local_contract", "demo")
PRODUCTION_PROBE_DATABASE_URL = (
    "postgresql://customer:customer@127.0.0.1:1/aicrm_customer_profile_phase3b_probe"
)

PROFILE_FORBIDDEN_HANDLER_CALLS = (
    "get_customer_via_legacy",
    "list_customers_via_legacy",
    "get_timeline_via_legacy",
    "recent_messages_via_legacy",
    "_context_for_lookup",
    "_context_for_external_userid",
    "_profile_payload_from_context",
)
TAGS_FORBIDDEN_HANDLER_CALLS = (
    "get_customer_via_legacy",
    "list_customers_via_legacy",
    "get_timeline_via_legacy",
    "recent_messages_via_legacy",
    "_context_for_lookup",
    "_context_for_external_userid",
    "_profile_tags_payload",
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
def production_customer_profile_probe_env():
    keys = {
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get(
            "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"
        ),
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": os.environ.get(
            "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"
        ),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
    }
    os.environ["AICRM_NEXT_ENV"] = "production"
    os.environ["DATABASE_URL"] = PRODUCTION_PROBE_DATABASE_URL
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ.pop("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", None)
    os.environ.setdefault("SECRET_KEY", "phase3b-customer-profile-readonly")
    os.environ.setdefault(
        "AUTOMATION_INTERNAL_API_TOKEN",
        "phase3b-customer-profile-readonly",
    )
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


def matching_route_methods(app: Any, *, path: str, endpoint_module: str) -> set[str]:
    methods: set[str] = set()
    for route in getattr(app, "routes", []):
        endpoint = getattr(route, "endpoint", None)
        if getattr(endpoint, "__module__", "") != endpoint_module:
            continue
        if getattr(route, "path", "") != path:
            continue
        methods.update(
            str(method).upper()
            for method in getattr(route, "methods", set()) or set()
        )
    return methods


def check_exact_route_owners(app: Any) -> dict[str, Any]:
    blockers: list[str] = []
    routes: list[dict[str, str]] = []
    for path, expected_module in TARGET_ROUTES.items():
        actual_module = first_matching_endpoint_module(app, method="GET", path=path)
        routes.append(
            {
                "path": path,
                "expected_module": expected_module,
                "actual_module": actual_module,
            }
        )
        if actual_module != expected_module:
            blockers.append(
                f"{path} resolved to {actual_module or 'no endpoint'}, expected {expected_module}"
            )
        if actual_module in {
            "aicrm_next.production_compat.api",
            "aicrm_next.integration_gateway.legacy_flask_facade",
        }:
            blockers.append(f"{path} is shadowed by compatibility facade endpoint {actual_module}")

        methods = matching_route_methods(app, path=path, endpoint_module=expected_module)
        state_methods = sorted(methods & STATE_CHANGING_METHODS)
        if state_methods:
            blockers.append(f"{path} exposes state-changing methods: {', '.join(state_methods)}")
    return {"ok": not blockers, "blockers": blockers, "routes": routes}


def check_response_headers(client: Any) -> dict[str, Any]:
    blockers: list[str] = []
    probes: list[dict[str, Any]] = []
    for path in TARGET_ROUTES:
        response = client.get(path, params={"external_userid": "wm_phase3b_probe"})
        record = {
            "path": path,
            "status_code": response.status_code,
            "route_owner_header": response.headers.get("X-AICRM-Route-Owner", ""),
            "compatibility_facade": response.headers.get("X-AICRM-Compatibility-Facade", ""),
        }
        probes.append(record)
        if record["route_owner_header"] != "ai_crm_next":
            blockers.append(f"{path} missing X-AICRM-Route-Owner=ai_crm_next")
        if record["compatibility_facade"] == "legacy_flask_facade":
            blockers.append(f"{path} returned legacy_flask_facade compatibility header")
    return {"ok": not blockers, "blockers": blockers, "probes": probes}


def check_input_errors(client: Any) -> dict[str, Any]:
    blockers: list[str] = []
    probes: list[dict[str, Any]] = []
    for path in TARGET_ROUTES:
        response = client.get(path)
        probes.append({"path": path, "status_code": response.status_code})
        if response.status_code != 400:
            blockers.append(f"{path} without required lookup input returned {response.status_code}, expected 400")
        if _contains_fixture_marker(response.text):
            blockers.append(f"{path} input error response contains fixture/local_contract/demo marker")
    return {"ok": not blockers, "blockers": blockers, "probes": probes}


def _json_or_text(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def check_production_unavailable_behavior(client: Any) -> dict[str, Any]:
    blockers: list[str] = []
    probes: list[dict[str, Any]] = []
    for path in TARGET_ROUTES:
        response = client.get(path, params={"external_userid": "wm_phase3b_probe"})
        body = _json_or_text(response)
        body_text = (
            json.dumps(body, ensure_ascii=False, sort_keys=True)
            if not isinstance(body, str)
            else body
        )
        source_status = body.get("source_status", "") if isinstance(body, dict) else ""
        record = {
            "path": path,
            "status_code": response.status_code,
            "source_status": source_status,
            "degraded": bool(body.get("degraded")) if isinstance(body, dict) else False,
            "fixture_marker_present": _contains_fixture_marker(body_text),
        }
        probes.append(record)
        if response.status_code == 200 and record["fixture_marker_present"]:
            blockers.append(
                f"{path} returned 200 with fixture/local_contract/demo marker in production probe"
            )
        if response.status_code == 200 and source_status in {"fixture", "local_contract", "demo"}:
            blockers.append(f"{path} returned 200 fake success source_status={source_status}")
        if response.status_code >= 500 and record["fixture_marker_present"]:
            blockers.append(f"{path} degraded/error response contains fixture/local_contract/demo marker")
    return {"ok": not blockers, "blockers": blockers, "probes": probes}


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
    customer_api = ROOT / "aicrm_next/customer_read_model/api.py"
    customer_source = _read(customer_api)

    profile_source = _function_source(customer_source, "get_admin_customer_profile")
    if not profile_source:
        blockers.append(f"{_rel(customer_api)} missing get_admin_customer_profile endpoint")
    for forbidden in PROFILE_FORBIDDEN_HANDLER_CALLS:
        if forbidden in profile_source:
            blockers.append(f"{_rel(customer_api)} get_admin_customer_profile directly calls {forbidden}")
    if "GetAdminCustomerProfileQuery" not in profile_source or "JSONResponse" not in profile_source:
        blockers.append(
            f"{_rel(customer_api)} get_admin_customer_profile must call GetAdminCustomerProfileQuery and serialize JSONResponse"
        )

    tags_source = _function_source(customer_source, "get_admin_customer_profile_tags")
    if not tags_source:
        blockers.append(f"{_rel(customer_api)} missing get_admin_customer_profile_tags endpoint")
    for forbidden in TAGS_FORBIDDEN_HANDLER_CALLS:
        if forbidden in tags_source:
            blockers.append(f"{_rel(customer_api)} get_admin_customer_profile_tags directly calls {forbidden}")
    if "GetAdminCustomerProfileTagsQuery" not in tags_source or "JSONResponse" not in tags_source:
        blockers.append(
            f"{_rel(customer_api)} get_admin_customer_profile_tags must call GetAdminCustomerProfileTagsQuery and serialize JSONResponse"
        )

    application = ROOT / "aicrm_next/customer_read_model/application.py"
    application_source = _read(application)
    for expected in ("class GetAdminCustomerProfileQuery", "class GetAdminCustomerProfileTagsQuery"):
        if expected not in application_source:
            blockers.append(f"{_rel(application)} missing {expected}")

    production_compat = ROOT / "aicrm_next/production_compat/api.py"
    production_compat_source = _read(production_compat)
    required_snippets = (
        '@wildcard_router.api_route("/api/sidebar/{path:path}", methods=_ALL_METHODS)',
        '@wildcard_router.api_route("/api/admin/customers/profile", methods=_ALL_METHODS)',
        '@wildcard_router.api_route("/api/admin/customers/profile/{path:path}", methods=_ALL_METHODS)',
        "async def legacy_production_compat_routes",
        "return await forward_to_legacy_flask(request)",
    )
    for snippet in required_snippets:
        if snippet not in production_compat_source:
            blockers.append(f"{_rel(production_compat)} missing expected wildcard behavior: {snippet}")

    return {"ok": not blockers, "blockers": blockers}


def run_fastapi_probes() -> dict[str, Any]:
    try:
        with production_customer_profile_probe_env():
            client = _make_client()
            checks = {
                "exact_route_owners": check_exact_route_owners(client.app),
                "response_headers": check_response_headers(client),
                "input_errors": check_input_errors(client),
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
        "target_routes": [
            {"method": "GET", "path": path, "expected_endpoint_module": module}
            for path, module in TARGET_ROUTES.items()
        ],
        "blockers": blockers,
        "static": static,
        "fastapi_probes": fastapi,
    }


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 3B Customer Profile Readonly Check",
        "",
        f"- overall: {report['overall']}",
        f"- blockers: {len(report.get('blockers', []))}",
        "",
        "## Target Routes",
    ]
    for route in report.get("target_routes", []):
        lines.append(
            f"- {route['method']} {route['path']} -> `{route['expected_endpoint_module']}`"
        )
    lines.extend(["", "## Blockers"])
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
