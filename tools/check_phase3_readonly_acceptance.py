#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ACCEPTANCE_YAML = ROOT / "docs/development/phase_3_readonly_replacement_acceptance_report.yaml"
ACCEPTANCE_MD = ROOT / "docs/development/phase_3_readonly_replacement_acceptance_report.md"
REQUIRED_DOCS = [
    ACCEPTANCE_MD,
    ACCEPTANCE_YAML,
    ROOT / "docs/development/phase_3_sidebar_readonly_replacement_spike.md",
    ROOT / "docs/development/phase_3b_customer_profile_readonly_hardening.md",
    ROOT / "docs/development/phase_3c_customer_read_model_readonly_hardening.md",
    ROOT / "docs/development/phase_3d_recent_messages_readonly_hardening.md",
]

EXPECTED_ROUTES = [
    {
        "phase": "phase_3a_sidebar_readonly",
        "route_pattern": "/api/sidebar/contact-binding-status",
        "method": "GET",
        "capability_owner": "aicrm_next.identity_contact",
        "endpoint_module": "aicrm_next.identity_contact.api",
        "checker": "tools/check_phase3_sidebar_readonly_replacement.py",
    },
    {
        "phase": "phase_3a_sidebar_readonly",
        "route_pattern": "/api/sidebar/customer-context",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3_sidebar_readonly_replacement.py",
    },
    {
        "phase": "phase_3b_customer_profile_readonly",
        "route_pattern": "/api/admin/customers/profile",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3b_customer_profile_readonly.py",
    },
    {
        "phase": "phase_3b_customer_profile_readonly",
        "route_pattern": "/api/admin/customers/profile/tags",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3b_customer_profile_readonly.py",
    },
    {
        "phase": "phase_3c_customer_read_model_readonly",
        "route_pattern": "/api/customers",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3c_customer_read_model_readonly.py",
    },
    {
        "phase": "phase_3c_customer_read_model_readonly",
        "route_pattern": "/api/customers/{external_userid}",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3c_customer_read_model_readonly.py",
    },
    {
        "phase": "phase_3c_customer_read_model_readonly",
        "route_pattern": "/api/customers/{external_userid}/timeline",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3c_customer_read_model_readonly.py",
    },
    {
        "phase": "phase_3d_recent_messages_readonly",
        "route_pattern": "/api/messages/{external_userid}/recent",
        "method": "GET",
        "capability_owner": "aicrm_next.customer_read_model",
        "endpoint_module": "aicrm_next.customer_read_model.api",
        "checker": "tools/check_phase3d_recent_messages_readonly.py",
    },
]

EXPECTED_CHECKERS = sorted({route["checker"] for route in EXPECTED_ROUTES})
BOOLEAN_REQUIRED = {
    "legacy_fallback_retained": True,
    "production_compat_unchanged": True,
    "delete_ready": False,
    "exact_next_owner_required": True,
    "compatibility_facade_header_allowed": False,
    "production_unavailable_must_degrade": True,
    "fixture_success_blocked": True,
    "real_external_calls_allowed": False,
}
FIXTURE_MARKERS = ("fixture", "local_contract", "demo")
PRODUCTION_PROBE_DATABASE_URL = (
    "postgresql://phase3:phase3@127.0.0.1:1/aicrm_phase3_acceptance_probe"
)
ACCEPTANCE_PROBES = [
    {
        "route_pattern": "/api/sidebar/contact-binding-status",
        "probe_path": "/api/sidebar/contact-binding-status?external_userid=external-phase3-acceptance",
    },
    {
        "route_pattern": "/api/sidebar/customer-context",
        "probe_path": "/api/sidebar/customer-context?external_userid=external-phase3-acceptance",
    },
    {
        "route_pattern": "/api/admin/customers/profile",
        "probe_path": "/api/admin/customers/profile?external_userid=external-phase3-acceptance",
    },
    {
        "route_pattern": "/api/admin/customers/profile/tags",
        "probe_path": "/api/admin/customers/profile/tags?external_userid=external-phase3-acceptance",
    },
    {
        "route_pattern": "/api/customers",
        "probe_path": "/api/customers?limit=1",
    },
    {
        "route_pattern": "/api/customers/{external_userid}",
        "probe_path": "/api/customers/external-phase3-acceptance",
    },
    {
        "route_pattern": "/api/customers/{external_userid}/timeline",
        "probe_path": "/api/customers/external-phase3-acceptance/timeline",
    },
    {
        "route_pattern": "/api/messages/{external_userid}/recent",
        "probe_path": "/api/messages/external-phase3-acceptance/recent?limit=2",
    },
]


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
def production_phase3_acceptance_probe_env():
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
    os.environ.setdefault("SECRET_KEY", "phase3-readonly-acceptance")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "phase3-readonly-acceptance")
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


def _json_or_text(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value.isdigit():
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return value.strip('"').strip("'")


def _load_yaml_without_dependency(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_section: str | None = None
    current_item: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" "):
            key, _, value = raw_line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                data[key] = _parse_scalar(value)
                current_section = None
            else:
                data[key] = []
                current_section = key
            current_item = None
            continue
        if current_section and raw_line.startswith("  - "):
            item_text = raw_line[4:]
            key, _, value = item_text.partition(":")
            current_item = {key.strip(): _parse_scalar(value.strip())}
            data[current_section].append(current_item)
            continue
        if current_item is not None and raw_line.startswith("    "):
            item_text = raw_line.strip()
            key, _, value = item_text.partition(":")
            current_item[key.strip()] = _parse_scalar(value.strip())
    return data


def load_acceptance_yaml(path: Path = ACCEPTANCE_YAML) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(text)


def _route_key(route: dict[str, Any]) -> tuple[str, str]:
    return (str(route.get("method") or ""), str(route.get("route_pattern") or ""))


def _load_checker(path: str):
    checker_path = ROOT / path
    spec = importlib.util.spec_from_file_location(checker_path.stem, checker_path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"cannot load checker {path}")
    spec.loader.exec_module(module)
    return module


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


def _iter_probe_records(value: Any):
    if isinstance(value, dict):
        if "fixture_marker_present" in value or "compatibility_facade" in value:
            yield value
        for item in value.values():
            yield from _iter_probe_records(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_probe_records(item)


def check_acceptance_yaml() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not ACCEPTANCE_YAML.exists():
        return {"ok": False, "blockers": [f"{_rel(ACCEPTANCE_YAML)} missing"], "warnings": warnings}

    data = load_acceptance_yaml()
    if data.get("version") != 1:
        blockers.append("acceptance yaml version must be 1")
    if data.get("status") != "acceptance_report_only_no_runtime_change":
        blockers.append("acceptance yaml status must be acceptance_report_only_no_runtime_change")

    routes = list(data.get("routes") or [])
    expected_by_key = {_route_key(route): route for route in EXPECTED_ROUTES}
    actual_by_key = {_route_key(route): route for route in routes}
    if set(actual_by_key) != set(expected_by_key):
        blockers.append(
            "acceptance yaml route set mismatch: "
            f"expected={sorted(expected_by_key)} actual={sorted(actual_by_key)}"
        )
    if len(routes) != 8:
        blockers.append(f"acceptance yaml must contain exactly 8 routes, found {len(routes)}")

    required_fields = {
        "phase",
        "route_pattern",
        "method",
        "capability_owner",
        "endpoint_module",
        "checker",
        "legacy_fallback_retained",
        "production_compat_unchanged",
        "delete_ready",
        "exact_next_owner_required",
        "compatibility_facade_header_allowed",
        "production_unavailable_must_degrade",
        "fixture_success_blocked",
        "real_external_calls_allowed",
        "business_continuity_requirement",
        "rollback",
    }
    for route in routes:
        key = _route_key(route)
        missing = sorted(field for field in required_fields if field not in route)
        if missing:
            blockers.append(f"{key} missing required fields: {', '.join(missing)}")
            continue
        expected = expected_by_key.get(key)
        if expected:
            for field in ("phase", "capability_owner", "endpoint_module", "checker"):
                if route.get(field) != expected[field]:
                    blockers.append(f"{key} {field}={route.get(field)!r}, expected {expected[field]!r}")
        for field, expected_value in BOOLEAN_REQUIRED.items():
            if route.get(field) is not expected_value:
                blockers.append(f"{key} {field} must be {expected_value!r}")
        continuity = str(route.get("business_continuity_requirement") or "").lower()
        if not all(token in continuity for token in ("fallback", "parity", "checker", "smoke", "rollback")):
            blockers.append(f"{key} business continuity requirement must name fallback/parity/checker/smoke/rollback")

    candidates = list(data.get("next_candidates") or [])
    if len(candidates) < 5:
        blockers.append("acceptance yaml must include shell/navigation, readonly admin page, and defer candidates")
    for marker in ("/admin", "/admin/customers", "/sidebar/bind-mobile", "/admin/questionnaires"):
        if not any(candidate.get("route_pattern") == marker for candidate in candidates):
            blockers.append(f"next_candidates missing {marker}")
    if not any(str(candidate.get("category")) == "defer" for candidate in candidates):
        blockers.append("next_candidates missing defer category")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "routes": routes}


def check_required_docs() -> dict[str, Any]:
    blockers = [f"{_rel(path)} missing" for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not blockers, "blockers": blockers}


def check_acceptance_markdown() -> dict[str, Any]:
    blockers: list[str] = []
    if not ACCEPTANCE_MD.exists():
        return {"ok": False, "blockers": [f"{_rel(ACCEPTANCE_MD)} missing"]}
    text = _read(ACCEPTANCE_MD)
    for route in EXPECTED_ROUTES:
        if route["route_pattern"] not in text:
            blockers.append(f"{_rel(ACCEPTANCE_MD)} missing {route['route_pattern']}")
    for phrase in (
        "Phase 3A-D acceptance report only",
        "does not change runtime behavior",
        "Fallback remains required until parity, checker, smoke, rollback, and owner approval",
        "Do not delete `legacy_customer_read_facade`",
        "Do not narrow the `/api/messages*` wildcard",
        "Payment, OAuth, WeCom, media upload, timer, and automation execution remain deferred",
    ):
        if phrase not in text:
            blockers.append(f"{_rel(ACCEPTANCE_MD)} missing required phrase: {phrase}")
    return {"ok": not blockers, "blockers": blockers}


def check_fastapi_acceptance_probes() -> dict[str, Any]:
    blockers: list[str] = []
    probes: list[dict[str, Any]] = []
    try:
        with production_phase3_acceptance_probe_env():
            client = _make_client()
            data = load_acceptance_yaml()
            routes_by_pattern = {
                str(route.get("route_pattern")): route
                for route in data.get("routes", [])
            }
            for probe in ACCEPTANCE_PROBES:
                route_pattern = str(probe["route_pattern"])
                probe_path = str(probe["probe_path"])
                path_only = probe_path.split("?", 1)[0]
                acceptance = routes_by_pattern.get(route_pattern) or {}
                expected_module = str(acceptance.get("endpoint_module") or "")
                actual_module = first_matching_endpoint_module(client.app, method="GET", path=path_only)
                response = client.get(probe_path)
                body = _json_or_text(response)
                body_text = (
                    json.dumps(body, ensure_ascii=False, sort_keys=True)
                    if not isinstance(body, str)
                    else body
                )
                source_status = body.get("source_status", "") if isinstance(body, dict) else ""
                record = {
                    "route_pattern": route_pattern,
                    "probe_path": probe_path,
                    "status_code": response.status_code,
                    "source_status": source_status,
                    "endpoint_module": actual_module,
                    "expected_endpoint_module": expected_module,
                    "route_owner_header": response.headers.get("X-AICRM-Route-Owner", ""),
                    "compatibility_facade": response.headers.get("X-AICRM-Compatibility-Facade", ""),
                    "fixture_marker_present": _contains_fixture_marker(body_text),
                    "degraded": bool(body.get("degraded")) if isinstance(body, dict) else False,
                }
                probes.append(record)
                if actual_module != expected_module:
                    blockers.append(
                        f"{route_pattern} endpoint_module={actual_module or 'no endpoint'}, expected {expected_module}"
                    )
                if record["route_owner_header"] != "ai_crm_next":
                    blockers.append(f"{route_pattern} missing X-AICRM-Route-Owner=ai_crm_next")
                if record["compatibility_facade"] == "legacy_flask_facade":
                    blockers.append(f"{route_pattern} returned legacy_flask_facade compatibility header")
                if response.status_code == 200 and record["fixture_marker_present"]:
                    blockers.append(f"{route_pattern} returned 200 fixture/local_contract/demo fake success")
                if response.status_code == 200 and source_status in FIXTURE_MARKERS:
                    blockers.append(f"{route_pattern} returned 200 fake source_status={source_status}")
    except Exception as exc:
        return {
            "ok": False,
            "blockers": [f"fastapi_acceptance_probe_unavailable: {exc}"],
            "probes": probes,
        }
    return {"ok": not blockers, "blockers": blockers, "probes": probes}


def check_phase_reports() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    reports: dict[str, Any] = {}
    for checker in EXPECTED_CHECKERS:
        try:
            module = _load_checker(checker)
            report = module.build_report()
        except Exception as exc:
            blockers.append(f"{checker} failed to run: {exc}")
            continue
        reports[checker] = report
        if report.get("overall") != "PASS":
            blockers.append(f"{checker} overall={report.get('overall')}: {report.get('blockers')}")
        for record in _iter_probe_records(report):
            if record.get("compatibility_facade") == "legacy_flask_facade":
                blockers.append(f"{checker} returned legacy_flask_facade header for {record.get('path')}")
            if record.get("status_code") == 200 and record.get("fixture_marker_present"):
                blockers.append(f"{checker} returned 200 fixture/local_contract/demo success for {record.get('path')}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "reports": reports}


def check_static_non_goals() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    forbidden_runtime_files = {"aicrm_next/main.py", "aicrm_next/production_compat/api.py"}
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "origin/main", "--", *sorted(forbidden_runtime_files)],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        changed_forbidden = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
        for path in changed_forbidden:
            blockers.append(f"{path} must not be modified by Phase 3E")
    except Exception as exc:
        warnings.append(f"could not compare runtime files against origin/main: {exc}")

    production_compat_source = _read(ROOT / "aicrm_next/production_compat/api.py")
    required_snippets = (
        '@wildcard_router.api_route("/api/messages/{path:path}", methods=_ALL_METHODS)',
        '@wildcard_router.api_route("/api/sidebar/{path:path}", methods=_ALL_METHODS)',
        '@wildcard_router.api_route("/api/admin/customers/profile", methods=_ALL_METHODS)',
        '@wildcard_router.api_route("/api/admin/customers/profile/{path:path}", methods=_ALL_METHODS)',
        "async def legacy_production_compat_routes",
        "return await forward_to_legacy_flask(request)",
    )
    for snippet in required_snippets:
        if snippet not in production_compat_source:
            blockers.append(f"aicrm_next/production_compat/api.py missing expected unchanged snippet: {snippet}")

    combined = "\n".join(_read(path) for path in (ACCEPTANCE_YAML, ACCEPTANCE_MD) if path.exists())
    for marker in ("real_external_calls_allowed: true", "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC=1"):
        if marker in combined:
            blockers.append(f"acceptance artifacts must not enable real external calls marker={marker}")

    for path in (ROOT / "aicrm_next").glob("**/*.py"):
        if "integration_gateway/legacy_flask_facade.py" in path.as_posix():
            continue
        source = _read(path)
        if "import wecom_ability_service" in source or "from wecom_ability_service" in source:
            blockers.append(f"{_rel(path)} directly imports wecom_ability_service")

    handler_checks = {
        ROOT / "aicrm_next/identity_contact/api.py": ("get_sidebar_contact_binding_status",),
        ROOT / "aicrm_next/customer_read_model/api.py": (
            "get_sidebar_customer_context",
            "get_admin_customer_profile",
            "get_admin_customer_profile_tags",
            "list_customers",
            "get_customer",
            "get_customer_timeline",
            "get_recent_messages",
        ),
    }
    for path, function_names in handler_checks.items():
        source = _read(path)
        for function_name in function_names:
            function_source = _function_source(source, function_name)
            if "forward_to_legacy_flask" in function_source:
                blockers.append(f"{_rel(path)} {function_name} must not call route-level forward_to_legacy_flask")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}


def build_report() -> dict[str, Any]:
    docs_report = check_required_docs()
    yaml_report = check_acceptance_yaml()
    markdown_report = check_acceptance_markdown()
    static_report = check_static_non_goals()
    fastapi_report = check_fastapi_acceptance_probes()
    phase_report = check_phase_reports()
    blockers = (
        list(docs_report.get("blockers", []))
        + list(yaml_report.get("blockers", []))
        + list(markdown_report.get("blockers", []))
        + list(static_report.get("blockers", []))
        + list(fastapi_report.get("blockers", []))
        + list(phase_report.get("blockers", []))
    )
    warnings = (
        list(yaml_report.get("warnings", []))
        + list(static_report.get("warnings", []))
        + list(phase_report.get("warnings", []))
    )
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "total_routes": len(yaml_report.get("routes", [])),
        "expected_routes": EXPECTED_ROUTES,
        "blockers": blockers,
        "warnings": warnings,
        "required_docs": docs_report,
        "acceptance_yaml": yaml_report,
        "acceptance_markdown": markdown_report,
        "static_non_goals": static_report,
        "fastapi_acceptance_probes": fastapi_report,
        "phase_checkers": {
            "ok": phase_report.get("ok"),
            "blockers": phase_report.get("blockers", []),
            "checkers": {
                checker: {
                    "overall": report.get("overall"),
                    "blockers": report.get("blockers", []),
                    "warnings": report.get("warnings", []),
                }
                for checker, report in phase_report.get("reports", {}).items()
            },
        },
    }


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 3 Readonly Acceptance Check",
        "",
        f"- overall: {report['overall']}",
        f"- total_routes: {report.get('total_routes', 0)}",
        f"- blockers: {len(report.get('blockers', []))}",
        f"- warnings: {len(report.get('warnings', []))}",
        "",
        "## Routes",
    ]
    for route in report.get("expected_routes", []):
        lines.append(f"- {route['method']} {route['route_pattern']} -> `{route['endpoint_module']}`")
    lines.extend(["", "## Phase Checkers"])
    for checker, checker_report in report.get("phase_checkers", {}).get("checkers", {}).items():
        lines.append(f"- `{checker}`: {checker_report.get('overall')}")
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
    if report.get("warnings"):
        print("warnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
