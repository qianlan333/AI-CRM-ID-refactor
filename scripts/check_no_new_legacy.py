#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report
from aicrm_next.platform_foundation.route_registry.service import RouteRegistryService

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv310",
    "__pycache__",
    "docs",
    "migrations",
    "tests",
    "tools",
    "skills",
    "experiments",
    "wecom_ability_service",
    "scripts",
}
LEGACY_IMPORT_ALLOWLIST = {
    Path("aicrm_next/production_compat/api.py"),
    Path("aicrm_next/frontend_compat/legacy_routes.py"),
    Path("aicrm_next/questionnaire/api.py"),
    Path("aicrm_next/automation_engine/group_ops/action_port.py"),
    Path("aicrm_next/automation_engine/group_ops/domain.py"),
    Path("aicrm_next/ai_assist/external_campaigns.py"),
    Path("aicrm_next/integration_gateway/legacy_flask_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_automation_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_questionnaire_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_sidebar_read_facade.py"),
    Path("aicrm_next/integration_gateway/wecom_group_adapter.py"),
}
WECOM_IMPORT_ALLOWLIST = {
    Path("app.py"),
    Path("legacy_flask_app.py"),
    Path("aicrm_next/automation_engine/audience_transition/repository.py"),
    Path("aicrm_next/automation_engine/audience_transition/integration_gateway.py"),
    Path("aicrm_next/automation_engine/audience_transition/application.py"),
    Path("aicrm_next/automation_engine/group_ops/integration_gateway.py"),
    Path("aicrm_next/automation_engine/group_ops/scheduler.py"),
    Path("aicrm_next/automation_engine/group_ops/action_port.py"),
    Path("aicrm_next/ai_assist/external_campaigns.py"),
    Path("aicrm_next/integration_gateway/questionnaire_adapters.py"),
    Path("aicrm_next/integration_gateway/wecom_group_adapter.py"),
    Path("aicrm_next/cloud_orchestrator/repository.py"),
}
API_SIDE_EFFECT_ALLOWLIST = {
    Path("aicrm_next/production_compat/api.py"),
}
SIDE_EFFECT_MARKERS = {
    "dispatch_wecom_task",
    "create_contact_way",
    "requests.post(",
    "requests.put(",
    "requests.patch(",
    "requests.delete(",
    "httpx.post(",
    "httpx.put(",
    "httpx.patch(",
    "httpx.delete(",
}
CUSTOMER_READ_ROLLBACK_FLAG = "CUSTOMER_READ_MODEL" + "_LEGACY_ROLLBACK_ENABLED"
MESSAGES_BROAD_WILDCARD = "/api/messages*"
MESSAGES_BROAD_WILDCARD_RUNTIME = "/api/messages/{path:path}"
SIDEBAR_READONLY_ROUTES = (
    "/api/sidebar/customer-context",
    "/api/sidebar/profile",
    "/api/sidebar/tags",
    "/api/sidebar/binding-status",
    "/api/sidebar/contact-binding-status",
    "/api/sidebar/lead-pool/status",
    "/api/sidebar/signup-tags/status",
    "/api/sidebar/marketing-status",
)
SIDEBAR_WRITE_ROUTES = (
    "/api/sidebar/bind-mobile",
    "/api/sidebar/lead-pool/upsert-class-term",
    "/api/sidebar/signup-tags/mark",
    "/api/sidebar/marketing-status/set-followup-segment",
    "/api/sidebar/marketing-status/mark-enrolled",
    "/api/sidebar/marketing-status/unmark-enrolled",
    "/api/sidebar/v2/profile",
    "/api/sidebar/v2/materials/send",
)
SIDEBAR_JSSDK_ROUTE = "/api/sidebar/jssdk-config"


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    detail: str
    remediation: str = "Register the route in the route registry and update the deletion lifecycle; do not add new legacy fallback or direct side-effect paths."

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _iter_python_files(root: Path) -> Iterable[Path]:
    candidates: list[Path] = []
    for item in [root / "aicrm_next", root / "app.py", root / "legacy_flask_app.py"]:
        if item.is_file():
            candidates.append(item)
        elif item.is_dir():
            candidates.extend(item.rglob("*.py"))
    for path in candidates:
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_DIRS:
            continue
        yield path


def scan_source_tree(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_python_files(root):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if "legacy_flask_facade" in text and rel not in LEGACY_IMPORT_ALLOWLIST:
            violations.append(Violation("legacy_flask_facade_import", str(rel), "legacy Flask facade import is not allowlisted"))
        if "wecom_ability_service" in text and rel not in WECOM_IMPORT_ALLOWLIST:
            violations.append(Violation("wecom_ability_service_import", str(rel), "legacy wecom_ability_service import is not allowlisted"))
        if rel.name in {"api.py", "routes.py"} and rel not in API_SIDE_EFFECT_ALLOWLIST:
            for marker in SIDE_EFFECT_MARKERS:
                if marker in text:
                    violations.append(Violation("api_direct_external_side_effect", str(rel), marker))
    return violations


def check_customer_read_model_legacy_deletion(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    customer_read_root = root / "aicrm_next/customer_read_model"
    for path in customer_read_root.rglob("*.py"):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if "legacy_customer_read_facade" in text:
            violations.append(Violation("customer_read_legacy_facade_import", str(rel), "customer_read_model must not import legacy_customer_read_facade"))
        if CUSTOMER_READ_ROLLBACK_FLAG in text:
            violations.append(Violation("customer_read_legacy_rollback_flag", str(rel), "customer read legacy rollback flag has been deleted"))
        if "LegacyShadowCustomerReadModelSource" in text:
            violations.append(Violation("customer_read_legacy_shadow_source", str(rel), "legacy shadow backfill source has been deleted"))

    backfill_script = root / "scripts/backfill_customer_read_model.py"
    if backfill_script.exists():
        text = backfill_script.read_text(encoding="utf-8")
        if "settings.database_url" in text or "get_settings().database_url" in text:
            violations.append(Violation("customer_read_backfill_execute_uses_default_database", str(backfill_script.relative_to(root)), "--execute must use explicit --database-url only"))
        if "legacy-shadow" in text or "LegacyShadowCustomerReadModelSource" in text:
            violations.append(Violation("customer_read_backfill_legacy_source", str(backfill_script.relative_to(root)), "backfill CLI must not expose legacy-shadow source"))

    service = RouteRegistryService()
    protected_paths = {
        "/api/customers",
        "/api/customers/{external_userid}",
        "/api/customers/{external_userid}/timeline",
        "/api/messages/{external_userid}/recent",
        "/admin/customers*",
    }
    for entry in service.list_routes():
        if entry.path_pattern in protected_paths and entry.legacy_fallback_allowed:
            violations.append(Violation("customer_read_route_legacy_fallback_allowed", entry.path_pattern, "customer read routes must not allow legacy fallback after deletion"))
    return violations


def _decorator_route_paths(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    route_paths: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func
            if not isinstance(attr, ast.Attribute) or attr.attr != "api_route":
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                route_paths.append(first.value)
    return route_paths


def _decorated_route_function_sources(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    route_sources: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_paths: list[str] = []
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func
            if not isinstance(attr, ast.Attribute) or attr.attr not in {"get", "api_route"}:
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                route_paths.append(first.value)
        if not route_paths:
            continue
        source = ast.get_source_segment(text, node) or ""
        for route_path in route_paths:
            route_sources.setdefault(route_path, []).append(source)
    return route_sources


def check_production_compat_routes(root: Path = ROOT) -> list[Violation]:
    service = RouteRegistryService()
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    for route_path in _decorator_route_paths(compat_path):
        entry = service.find_route(route_path, None)
        if not entry:
            violations.append(Violation("production_compat_route_not_registered", str(compat_path.relative_to(root)), route_path))
            continue
        if entry.runtime_owner != "production_compat" and not entry.legacy_fallback_allowed:
            violations.append(Violation("production_compat_route_owner_mismatch", str(compat_path.relative_to(root)), route_path))
        if "{path:path}" in route_path and not entry.legacy_fallback_allowed:
            violations.append(Violation("undocumented_wildcard_fallback", str(compat_path.relative_to(root)), route_path))
    return violations


def _load_yaml_records(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = payload.get(key) or []
    return [record for record in records if isinstance(record, dict)]


def check_messages_broad_wildcard_deletion(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        text = compat_path.read_text(encoding="utf-8")
        forbidden_decorators = (
            '@wildcard_router.api_route("/api/messages/{path:path}"',
            "@wildcard_router.api_route('/api/messages/{path:path}'",
        )
        for marker in forbidden_decorators:
            if marker in text:
                violations.append(
                    Violation(
                        "messages_broad_wildcard_decorator",
                        str(compat_path.relative_to(root)),
                        marker,
                        "Remove the /api/messages/{path:path} production_compat wildcard; exact Next routes own messages surfaces.",
                    )
                )
        if MESSAGES_BROAD_WILDCARD_RUNTIME in text and "forward_to_legacy_flask" in text:
            violations.append(
                Violation(
                    "messages_broad_wildcard_legacy_forward",
                    str(compat_path.relative_to(root)),
                    MESSAGES_BROAD_WILDCARD_RUNTIME,
                    "Do not reintroduce /api/messages/{path:path} forwarding to the legacy Flask facade.",
                )
            )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_record = next((record for record in registry_records if record.get("path_pattern") == MESSAGES_BROAD_WILDCARD), None)
    if registry_record is None:
        violations.append(
            Violation(
                "messages_broad_wildcard_registry_record_missing",
                "docs/architecture/legacy_exit_route_registry.yaml",
                MESSAGES_BROAD_WILDCARD,
                "Keep a deletion record for /api/messages* and mark it legacy_deleted or deletion_locked.",
            )
        )
    else:
        if registry_record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("messages_broad_wildcard_registry_legacy_allowed", MESSAGES_BROAD_WILDCARD, "legacy_fallback_allowed=true"))
        if registry_record.get("runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("messages_broad_wildcard_registry_owner", MESSAGES_BROAD_WILDCARD, f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("delete_status") not in {"legacy_deleted", "deletion_locked"}:
            violations.append(Violation("messages_broad_wildcard_registry_delete_status", MESSAGES_BROAD_WILDCARD, f"delete_status={registry_record.get('delete_status')}"))
        if registry_record.get("replacement_status") not in {"deleted", "locked"}:
            violations.append(Violation("messages_broad_wildcard_registry_replacement_status", MESSAGES_BROAD_WILDCARD, f"replacement_status={registry_record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_record = next((record for record in manifest_records if record.get("route_pattern") == MESSAGES_BROAD_WILDCARD), None)
    if manifest_record is None:
        violations.append(
            Violation(
                "messages_broad_wildcard_manifest_record_missing",
                "docs/route_ownership/production_route_ownership_manifest.yaml",
                MESSAGES_BROAD_WILDCARD,
                "Keep a production manifest deletion record for /api/messages*.",
            )
        )
    else:
        if manifest_record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("messages_broad_wildcard_manifest_legacy_allowed", MESSAGES_BROAD_WILDCARD, "legacy_fallback_allowed=true"))
        if manifest_record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("messages_broad_wildcard_manifest_legacy_forward", MESSAGES_BROAD_WILDCARD, "production_behavior=legacy_forward"))
        if manifest_record.get("current_runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("messages_broad_wildcard_manifest_owner", MESSAGES_BROAD_WILDCARD, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("delete_ready") is not True:
            violations.append(Violation("messages_broad_wildcard_manifest_not_delete_ready", MESSAGES_BROAD_WILDCARD, f"delete_ready={manifest_record.get('delete_ready')}"))

    return violations


def check_sidebar_readonly_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path in _decorator_route_paths(compat_path):
            if route_path in SIDEBAR_READONLY_ROUTES:
                violations.append(
                    Violation(
                        "sidebar_readonly_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Sidebar readonly exact routes are locked to Next-native owners and must not reappear in production_compat.",
                    )
                )
            if route_path in SIDEBAR_WRITE_ROUTES:
                violations.append(
                    Violation(
                        "sidebar_write_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Sidebar write exact routes are deletion_locked to Next CommandBus and must not reappear in production_compat. JSSDK remains the only sidebar exact production_compat exception in this closeout.",
                    )
                )

    for api_path in [
        root / "aicrm_next/customer_read_model/api.py",
        root / "aicrm_next/identity_contact/api.py",
    ]:
        if not api_path.exists():
            continue
        for route_path, function_sources in _decorated_route_function_sources(api_path).items():
            if route_path not in SIDEBAR_READONLY_ROUTES:
                continue
            for source in function_sources:
                forbidden_markers = {
                    "legacy_sidebar_read_facade": "sidebar_readonly_legacy_facade",
                    "forward_to_legacy_flask": "sidebar_readonly_legacy_forward",
                    "production_compat": "sidebar_readonly_production_compat_reference",
                    "X-AICRM-Compatibility-Facade": "sidebar_readonly_compatibility_facade_header",
                    '"fallback_used": True': "sidebar_readonly_fallback_used_true",
                    "'fallback_used': True": "sidebar_readonly_fallback_used_true",
                }
                for marker, code in forbidden_markers.items():
                    if marker in source:
                        violations.append(
                            Violation(
                                code,
                                str(api_path.relative_to(root)),
                                f"{route_path}: {marker}",
                                "Sidebar readonly route handlers must stay Next-native, must not forward to legacy, and must not expose compatibility facade behavior.",
                            )
                        )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in SIDEBAR_READONLY_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_readonly_registry_record_missing",
                    "docs/architecture/legacy_exit_route_registry.yaml",
                    route_path,
                    "Keep sidebar readonly routes registered and locked as Next-native deletion_locked routes.",
                )
            )
            continue
        if record.get("runtime_owner") != "next_native":
            violations.append(Violation("sidebar_readonly_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_readonly_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("sidebar_readonly_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") not in {"locked", "validated"}:
            violations.append(Violation("sidebar_readonly_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in SIDEBAR_READONLY_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_readonly_manifest_record_missing",
                    "docs/route_ownership/production_route_ownership_manifest.yaml",
                    route_path,
                    "Keep sidebar readonly routes in the production manifest as Next-owned readonly routes.",
                )
            )
            continue
        if record.get("current_runtime_owner") not in {"next", "next_native"}:
            violations.append(Violation("sidebar_readonly_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("sidebar_readonly_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_readonly_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))

    for route_path in SIDEBAR_WRITE_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_write_manifest_record_missing",
                    "docs/route_ownership/production_route_ownership_manifest.yaml",
                    route_path,
                    "Keep sidebar write routes in the production manifest as Next CommandBus locked routes.",
                )
            )
            continue
        behavior = record.get("production_behavior")
        if record.get("current_runtime_owner") not in {"next", "next_native"}:
            violations.append(Violation("sidebar_write_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if behavior == "legacy_forward":
            violations.append(Violation("sidebar_write_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
        if behavior != "next_command":
            violations.append(Violation("sidebar_write_manifest_behavior", route_path, f"production_behavior={behavior}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_write_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True:
            violations.append(Violation("sidebar_write_manifest_not_delete_ready", route_path, f"delete_ready={record.get('delete_ready')}"))

    jssdk_record = manifest_by_path.get(SIDEBAR_JSSDK_ROUTE)
    if jssdk_record is not None:
        if jssdk_record.get("production_behavior") != "legacy_forward" or jssdk_record.get("delete_ready") is True:
            violations.append(
                Violation(
                    "sidebar_jssdk_mislocked_by_write_closeout",
                    SIDEBAR_JSSDK_ROUTE,
                    f"production_behavior={jssdk_record.get('production_behavior')} delete_ready={jssdk_record.get('delete_ready')}",
                    "Sidebar JSSDK signing is out of scope for sidebar write deletion closeout and must not be marked deleted or locked here.",
                )
            )

    for route_path in SIDEBAR_WRITE_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_write_registry_record_missing",
                    "docs/architecture/legacy_exit_route_registry.yaml",
                    route_path,
                    "Keep sidebar write routes registered as deletion_locked Next CommandBus routes.",
                )
            )
            continue
        if record.get("runtime_owner") != "next_native":
            violations.append(Violation("sidebar_write_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_write_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("sidebar_write_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") not in {"locked", "deleted"}:
            violations.append(Violation("sidebar_write_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("sidebar_write_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))

    sidebar_write_api = root / "aicrm_next/sidebar_write/api.py"
    sidebar_write_application = root / "aicrm_next/sidebar_write/application.py"
    for api_path in [sidebar_write_api, sidebar_write_application]:
        if not api_path.exists():
            continue
        text = api_path.read_text(encoding="utf-8")
        forbidden_markers = {
            "X-AICRM-Compatibility-Facade": "sidebar_write_compatibility_facade_header",
            '"fallback_used": True': "sidebar_write_fallback_used_true",
            "'fallback_used': True": "sidebar_write_fallback_used_true",
            '"real_external_call_executed": True': "sidebar_write_real_external_call_true",
            "'real_external_call_executed': True": "sidebar_write_real_external_call_true",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(api_path.relative_to(root)),
                        marker,
                        "Sidebar write routes must not expose compatibility facade behavior, fallback_used=true, or real external calls.",
                    )
                )

    return violations


def run_checks(*, strict: bool) -> dict:
    violations = (
        scan_source_tree(ROOT)
        + check_customer_read_model_legacy_deletion(ROOT)
        + check_production_compat_routes(ROOT)
        + check_messages_broad_wildcard_deletion(ROOT)
        + check_sidebar_readonly_closeout_lock(ROOT)
    )
    route_report = build_route_check_report(strict=strict)
    for item in route_report["blockers"]:
        violations.append(
            Violation(
                "route_registry_strict",
                "runtime",
                str(item),
                "Resolve the route diff through route registry ownership and lifecycle updates instead of adding undocumented fallback.",
            )
        )
    return {
        "ok": not violations,
        "strict": strict,
        "violations": [violation.to_dict() for violation in violations],
        "route_registry": {
            "ok": route_report["ok"],
            "mode": route_report["mode"],
            "registered_routes_count": route_report["registered_routes_count"],
            "manifest_routes_count": route_report["manifest_routes_count"],
            "undocumented_routes_count": len(route_report["undocumented_routes"]),
            "legacy_fallback_routes_count": len(route_report["legacy_fallback_routes"]),
            "wildcard_routes_count": len(route_report["wildcard_routes"]),
            "unknown_owner_routes_count": len(route_report["unknown_owner_routes"]),
            "deleted_but_still_registered_routes_count": len(route_report["deleted_but_still_registered_routes"]),
            "blockers": route_report["blockers"],
            "warnings": route_report["warnings"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Block new legacy imports, fallbacks, wildcard routes, and undocumented Next routes.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = run_checks(strict=bool(args.strict))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
