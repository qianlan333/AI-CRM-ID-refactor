#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from starlette.routing import Match

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"

NEXT_OWNED_BEHAVIORS = {"next_exact", "guarded_preview", "fake_adapter", "readonly_facade"}
PRODUCTION_COMPAT_BEHAVIORS = {"legacy_forward", "scheduled_safe_mode"}

RESOLUTION_SAMPLES = [
    ("GET", "/health"),
    ("GET", "/api/system/health"),
    ("GET", "/api/customers"),
    ("GET", "/api/customers/wx_ext_001"),
    ("GET", "/api/customers/wx_ext_001/timeline"),
    ("GET", "/api/messages/wx_ext_001/recent"),
    ("GET", "/api/admin/questionnaires"),
    ("GET", "/api/h5/questionnaires/hxc-activation-v1"),
    ("GET", "/api/h5/wechat/oauth/start"),
    ("GET", "/api/admin/automation-conversion/overview"),
    ("POST", "/api/admin/automation-conversion/programs/3/setup/basic"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/options"),
    ("GET", "/api/admin/automation-conversion/agents/options"),
    ("POST", "/api/customer-automation/activation-webhook"),
    ("GET", "/admin/wechat-pay/products"),
    ("GET", "/admin/wechat-pay/products/new"),
    ("GET", "/api/admin/wechat-pay/products"),
    ("GET", "/api/admin/wechat-pay/products/1"),
    ("GET", "/api/admin/wechat-pay/products/1/share"),
    ("GET", "/api/admin/image-library"),
    ("GET", "/api/admin/image-library/image_masked_001"),
    ("POST", "/api/admin/automation-conversion/jobs/run-due"),
    ("POST", "/wecom/external-contact/callback"),
    ("POST", "/api/wecom/events"),
    ("GET", "/api/h5/wechat-pay/legacy-probe"),
    ("GET", "/api/customers/automation/legacy-probe"),
    ("GET", "/sidebar/bind-mobile"),
    ("GET", "/api/sidebar/contact-binding-status"),
    ("GET", "/api/sidebar/customer-context"),
    ("GET", "/api/admin/customers/profile"),
    ("GET", "/api/admin/customers/profile/tags"),
    ("POST", "/api/sidebar/bind-mobile"),
]


@contextmanager
def production_route_env():
    keys = {
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
    }
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ.pop("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", None)
    os.environ.setdefault("DATABASE_URL", "postgresql://route:route@127.0.0.1:1/aicrm_route")
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("SECRET_KEY", "production-route-resolution")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "route-resolution-token")
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_manifest(path: Path | None = None) -> list[dict[str, Any]]:
    manifest = yaml.safe_load((path or MANIFEST).read_text(encoding="utf-8"))
    return list(manifest.get("routes") or [])


def collect_app_routes() -> list[dict[str, Any]]:
    with production_route_env():
        module = importlib.import_module("aicrm_next.main")
        app = module.create_app()
    routes: list[dict[str, Any]] = []
    for index, route in enumerate(app.routes):
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        module_name = getattr(endpoint, "__module__", "") if endpoint else ""
        name = getattr(endpoint, "__name__", "") if endpoint else ""
        methods = sorted((getattr(route, "methods", None) or set()) - {"HEAD"})
        if path:
            routes.append(
                {
                    "index": index,
                    "path": path,
                    "methods": methods,
                    "endpoint_module": module_name,
                    "endpoint_name": name,
                    "is_production_compat": module_name == "aicrm_next.production_compat.api",
                    "is_catch_all": "{path:path}" in path,
                    "_route": route,
                }
            )
    return routes


def public_route(route: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in route.items() if key != "_route"}


def first_matching_route(routes: list[dict[str, Any]], *, method: str, path: str) -> dict[str, Any] | None:
    scope = {"type": "http", "method": method.upper(), "path": path, "root_path": "", "headers": []}
    for route in routes:
        match, _ = route["_route"].matches(scope)
        if match != Match.NONE:
            return route
    return None


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*")
    escaped = re.sub(r"\\\{[^{}]+:path\\\}", ".*", escaped)
    escaped = re.sub(r"\\\{[^{}]+\\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def manifest_record_for_path(records: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    matches = [record for record in records if _pattern_to_regex(str(record["route_pattern"])).match(path)]
    if not matches:
        return None
    return sorted(matches, key=lambda item: len(str(item["route_pattern"]).replace("*", "")), reverse=True)[0]


def shadowed_exact_routes(routes: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shadowed: list[dict[str, Any]] = []
    for route in routes:
        if route["is_production_compat"] or route["is_catch_all"]:
            continue
        if "GET" not in route["methods"] and "POST" not in route["methods"]:
            continue
        method = "GET" if "GET" in route["methods"] else "POST"
        first = first_matching_route(routes, method=method, path=route["path"])
        if not first or not first["is_production_compat"]:
            continue
        manifest = manifest_record_for_path(records, route["path"]) or {}
        shadowed.append(
            {
                "method": method,
                "path": route["path"],
                "expected_endpoint_module": route["endpoint_module"],
                "caught_by": public_route(first),
                "manifest_route_pattern": manifest.get("route_pattern", ""),
                "manifest_current_runtime_owner": manifest.get("current_runtime_owner", ""),
                "manifest_production_behavior": manifest.get("production_behavior", ""),
            }
        )
    return shadowed


def resolution_samples(routes: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for method, path in RESOLUTION_SAMPLES:
        first = first_matching_route(routes, method=method, path=path)
        manifest = manifest_record_for_path(records, path) or {}
        samples.append(
            {
                "method": method,
                "path": path,
                "route_owner": "production_compat" if first and first["is_production_compat"] else "next",
                "endpoint_module": first["endpoint_module"] if first else "",
                "endpoint_name": first["endpoint_name"] if first else "",
                "matched_route_path": first["path"] if first else "",
                "manifest_route_pattern": manifest.get("route_pattern", ""),
                "manifest_current_runtime_owner": manifest.get("current_runtime_owner", ""),
                "manifest_production_behavior": manifest.get("production_behavior", ""),
            }
        )
    return samples


def run_check() -> dict[str, Any]:
    records = load_manifest()
    routes = collect_app_routes()
    shadowed = shadowed_exact_routes(routes, records)
    samples = resolution_samples(routes, records)
    blockers: list[str] = []
    warnings: list[str] = []

    for item in shadowed:
        behavior = str(item.get("manifest_production_behavior") or "")
        owner = str(item.get("manifest_current_runtime_owner") or "")
        if behavior == "next_exact":
            blockers.append(f"manifest_next_exact_caught_by_production_compat:{item['method']} {item['path']}")
        elif owner == "next" and behavior in NEXT_OWNED_BEHAVIORS:
            blockers.append(f"manifest_next_owned_exact_caught_by_production_compat:{item['method']} {item['path']}")

    for sample in samples:
        behavior = str(sample.get("manifest_production_behavior") or "")
        owner = str(sample.get("manifest_current_runtime_owner") or "")
        route_owner = str(sample.get("route_owner") or "")
        route_label = f"{sample['method']} {sample['path']}"
        if behavior == "next_exact" and route_owner == "production_compat":
            blockers.append(f"manifest_next_exact_sample_caught_by_production_compat:{route_label}")
        if owner == "production_compat" and behavior in PRODUCTION_COMPAT_BEHAVIORS and route_owner != "production_compat":
            blockers.append(f"manifest_production_compat_sample_not_forwarded:{route_label}")
        if owner == "next" and behavior in NEXT_OWNED_BEHAVIORS and route_owner == "production_compat":
            blockers.append(f"manifest_next_owned_sample_caught_by_production_compat:{route_label}")

    categories = {
        "must_legacy_forward": [record for record in records if record.get("production_behavior") == "legacy_forward"],
        "must_next_exact": [record for record in records if record.get("production_behavior") == "next_exact"],
        "must_guarded_or_blocked": [
            record
            for record in records
            if record.get("production_behavior") in {"guarded_preview", "scheduled_safe_mode", "fake_adapter", "local_contract_only"}
            or record.get("current_runtime_owner") == "blocked"
        ],
    }
    return {
        "ok": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": warnings,
        "route_count": len(routes),
        "production_compat_route_count": len([route for route in routes if route["is_production_compat"]]),
        "production_compat_catch_all_count": len([route for route in routes if route["is_production_compat"] and route["is_catch_all"]]),
        "shadowed_exact_routes": shadowed,
        "resolution_samples": samples,
        "categories": {
            name: [
                {
                    "route_pattern": record["route_pattern"],
                    "current_runtime_owner": record["current_runtime_owner"],
                    "production_behavior": record["production_behavior"],
                }
                for record in values
            ]
            for name, values in categories.items()
        },
    }


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Production Route Resolution",
            "",
            f"- ok: `{str(result['ok']).lower()}`",
            f"- route_count: `{result['route_count']}`",
            f"- production_compat_route_count: `{result['production_compat_route_count']}`",
            f"- production_compat_catch_all_count: `{result['production_compat_catch_all_count']}`",
            f"- blockers: `{len(result['blockers'])}`",
            "",
            "## Resolution Samples",
        ]
        for item in result["resolution_samples"]:
            lines.append(
                f"- {item['method']} {item['path']}: `{item['route_owner']}` -> "
                f"`{item['endpoint_module']}.{item['endpoint_name']}` "
                f"(manifest `{item['manifest_route_pattern']}` / `{item['manifest_production_behavior']}`)"
            )
        lines.extend(["", "## Shadowed Exact Routes"])
        if result["shadowed_exact_routes"]:
            for item in result["shadowed_exact_routes"]:
                lines.append(f"- {item['method']} {item['path']} caught by `{item['caught_by']['path']}`")
        else:
            lines.append("- none")
        lines.extend(["", "## Blockers"])
        lines.extend(f"- {item}" for item in result["blockers"])
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI-CRM Next production route resolution.")
    parser.add_argument("--output-md")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_check()
    write_outputs(result, args.output_md, args.output_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
