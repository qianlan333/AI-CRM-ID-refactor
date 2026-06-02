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
USER_OPS_READONLY_ROUTES = (
    "/api/admin/user-ops/overview",
    "/api/admin/user-ops/cards",
    "/api/admin/user-ops/customers",
    "/api/admin/user-ops/customers/{external_userid}",
    "/api/admin/user-ops/customers/{external_userid}/timeline",
    "/api/admin/user-ops/filters",
    "/api/admin/user-ops/send-records",
)
USER_OPS_PREVIEW_ROUTES = (
    "/api/admin/user-ops/broadcast/preview",
    "/api/admin/user-ops/export/preview",
)
QUESTIONNAIRE_ADMIN_READ_ROUTES = (
    "/admin/questionnaires",
    "/admin/questionnaires/new",
    "/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires",
    "/api/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires/{questionnaire_id}/questions",
    "/api/admin/questionnaires/{questionnaire_id}/results",
    "/api/admin/questionnaires/{questionnaire_id}/submissions",
)
QUESTIONNAIRE_ADMIN_WRITE_ROUTES = (
    "/api/admin/questionnaires",
    "/api/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires/{questionnaire_id}/duplicate",
    "/api/admin/questionnaires/{questionnaire_id}/publish",
    "/api/admin/questionnaires/{questionnaire_id}/enable",
    "/api/admin/questionnaires/{questionnaire_id}/disable",
    "/api/admin/questionnaires/{questionnaire_id}/export/preview",
    "/api/admin/questionnaires/{questionnaire_id}/export",
)
QUESTIONNAIRE_H5_COMMAND_ROUTES = (
    "/api/h5/questionnaires/{slug}/submit",
    "/api/h5/questionnaires/{slug}/client-diagnostics",
)
QUESTIONNAIRE_OAUTH_EXACT_ROUTES = (
    "/api/h5/wechat/oauth/start",
    "/api/h5/wechat/oauth/callback",
)
QUESTIONNAIRE_OUT_OF_SCOPE_ROUTES = (
    "/api/h5/wechat/oauth*",
)


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


def _function_sources(path: Path, names: set[str]) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    sources: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            sources[node.name] = ast.get_source_segment(text, node) or ""
    return sources


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


def check_user_ops_next_native_preview(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path.startswith("/api/admin/user-ops") or route_path.startswith("/admin/user-ops"):
                violations.append(
                    Violation(
                        "user_ops_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "User Ops group 6 routes must stay in Next ops_enrollment/frontend_compat and must not be added to production_compat.",
                    )
                )

    ops_root = root / "aicrm_next/ops_enrollment"
    for path in ops_root.rglob("*.py") if ops_root.exists() else []:
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        forbidden_markers = {
            "forward_to_legacy_flask": "user_ops_legacy_forward",
            "legacy_flask_facade": "user_ops_legacy_facade",
            '"fallback_used": True': "user_ops_fallback_used_true",
            "'fallback_used': True": "user_ops_fallback_used_true",
            '"real_external_call_executed": True': "user_ops_real_external_call_true",
            "'real_external_call_executed': True": "user_ops_real_external_call_true",
            "real_enabled": "user_ops_real_enabled_marker",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(rel),
                        marker,
                        "User Ops read/preview routes must not use legacy forward, fallback_used=true, or real external-call enablement.",
                    )
                )
    application_path = ops_root / "application.py"
    if application_path.exists():
        preview_sources = _function_sources(application_path, {"_handle_broadcast_preview", "_handle_export_preview"})
        forbidden_preview_markers = {
            "real_external_call_executed=true": "user_ops_preview_real_external_call_true",
            "real_external_call_executed': true": "user_ops_preview_real_external_call_true",
            'real_external_call_executed": true': "user_ops_preview_real_external_call_true",
            "real_enabled default": "user_ops_preview_real_enabled_default",
            "default real_enabled": "user_ops_preview_real_enabled_default",
            "send_private_message(": "user_ops_preview_direct_wecom_send",
            "dispatch_wecom_task(": "user_ops_preview_direct_wecom_send",
            "requests.post(": "user_ops_preview_direct_wecom_send",
            "httpx.post(": "user_ops_preview_direct_wecom_send",
            "open(": "user_ops_preview_direct_storage_write",
            "write_text(": "user_ops_preview_direct_storage_write",
            "write_bytes(": "user_ops_preview_direct_storage_write",
            "upload_file(": "user_ops_preview_direct_storage_write",
        }
        for function_name, source in preview_sources.items():
            normalized = " ".join(source.lower().split())
            for marker, code in forbidden_preview_markers.items():
                if marker in normalized:
                    violations.append(
                        Violation(
                            code,
                            str(application_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "User Ops preview handlers must stay SideEffectPlan-only with real external calls and storage writes blocked.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    readonly_records = {"/admin/user-ops": "frontend_compat", **{route: "next_native" for route in USER_OPS_READONLY_ROUTES}}
    for route_path, expected_owner in readonly_records.items():
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_registry_readonly_record_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != expected_owner:
            violations.append(Violation("user_ops_registry_readonly_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_registry_readonly_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("user_ops_registry_readonly_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_registry_readonly_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    for record in registry_records:
        route_path = str(record.get("path_pattern") or "")
        if not (route_path.startswith("/api/admin/user-ops") or route_path.startswith("/admin/user-ops")):
            continue
        if route_path in {"/api/admin/user-ops*", "/admin/user-ops*"}:
            continue
        if record.get("runtime_owner") == "production_compat" or record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("user_ops_registry_legacy_rollback_reintroduced", route_path, f"runtime_owner={record.get('runtime_owner')} legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
    for route_path in USER_OPS_PREVIEW_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_preview_registry_record_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != "next_native":
            violations.append(Violation("user_ops_preview_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_preview_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("user_ops_preview_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("user_ops_preview_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_preview_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in readonly_records:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_manifest_readonly_record_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") == "production_compat" or record.get("production_behavior") == "legacy_forward" or record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_manifest_readonly_legacy_forward", route_path, f"current_runtime_owner={record.get('current_runtime_owner')} production_behavior={record.get('production_behavior')} legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_manifest_readonly_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    for record in manifest_records:
        route_path = str(record.get("route_pattern") or "")
        if not (route_path.startswith("/api/admin/user-ops") or route_path.startswith("/admin/user-ops")):
            continue
        if route_path in {"/api/admin/user-ops*", "/admin/user-ops*"}:
            continue
        if record.get("current_runtime_owner") == "production_compat" or record.get("production_behavior") == "legacy_forward" or record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("user_ops_manifest_legacy_rollback_reintroduced", route_path, f"current_runtime_owner={record.get('current_runtime_owner')} production_behavior={record.get('production_behavior')} legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
    for route_path in USER_OPS_PREVIEW_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_preview_manifest_record_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("user_ops_preview_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_preview_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_preview_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("user_ops_preview_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
    return violations


def check_questionnaire_admin_read_next_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in QUESTIONNAIRE_ADMIN_READ_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_admin_read_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire admin read routes must stay in frontend_compat/questionnaire Next read model code, not production_compat.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    if api_path.exists():
        sources = _function_sources(
            api_path,
            {
                "list_questionnaires",
                "get_questionnaire",
                "get_questionnaire_questions",
                "get_questionnaire_results",
                "get_questionnaire_submissions",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_admin_read_legacy_forward",
            "list_questionnaires_from_legacy": "questionnaire_admin_read_legacy_facade",
            "get_questionnaire_detail_from_legacy": "questionnaire_admin_read_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_admin_read_compatibility_facade",
            '"fallback_used": True': "questionnaire_admin_read_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_read_fallback_used_true",
            "create_questionnaire_in_legacy": "questionnaire_admin_read_write_facade",
            "update_questionnaire_in_legacy": "questionnaire_admin_read_write_facade",
            "delete_questionnaire_in_legacy": "questionnaire_admin_read_write_facade",
            "requests.post(": "questionnaire_admin_read_direct_external_call",
            "httpx.post(": "questionnaire_admin_read_direct_external_call",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire admin read handlers must stay Next-query/read-model only with no legacy forward or direct side effects.",
                        )
                    )

    frontend_path = root / "aicrm_next/frontend_compat/legacy_routes.py"
    if frontend_path.exists():
        sources = _function_sources(
            frontend_path,
            {
                "admin_questionnaires",
                "admin_questionnaire_new",
                "admin_questionnaire_detail",
                "_questionnaire_editor_response",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_admin_read_page_legacy_forward",
            "list_questionnaires_from_legacy": "questionnaire_admin_read_page_legacy_facade",
            "get_questionnaire_detail_from_legacy": "questionnaire_admin_read_page_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_admin_read_page_compatibility_facade",
            '"fallback_used": True': "questionnaire_admin_read_page_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_read_page_fallback_used_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(frontend_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire admin read pages must stay Next-query/read-model only with no legacy forward, compatibility facade, or fallback_used=true.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in QUESTIONNAIRE_ADMIN_READ_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_admin_read_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        expected_owner = "frontend_compat" if route_path.startswith("/admin/") else "next_native"
        if record.get("runtime_owner") != expected_owner:
            violations.append(Violation("questionnaire_admin_read_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_read_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source"):
            violations.append(Violation("questionnaire_admin_read_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("questionnaire_admin_read_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_read_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    for route_path in QUESTIONNAIRE_OUT_OF_SCOPE_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            continue
        if record.get("delete_status") == "deletion_locked" or record.get("replacement_status") == "locked":
            violations.append(Violation("questionnaire_out_of_scope_route_locked", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in QUESTIONNAIRE_ADMIN_READ_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_admin_read_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") not in {"next", "next_native", "frontend_compat"}:
            violations.append(Violation("questionnaire_admin_read_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("questionnaire_admin_read_manifest_legacy_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("production_behavior") != "next_read_model_only":
            violations.append(Violation("questionnaire_admin_read_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_read_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_read_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_questionnaire_admin_write_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path.startswith("/api/admin/questionnaires") and route_path not in QUESTIONNAIRE_ADMIN_READ_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_admin_write_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire admin write routes are deletion_locked to Next CommandBus; do not add production_compat handlers.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    if api_path.exists():
        sources = _function_sources(
            api_path,
            {
                "create_questionnaire",
                "update_questionnaire",
                "duplicate_questionnaire",
                "publish_questionnaire",
                "disable_questionnaire",
                "enable_questionnaire",
                "delete_questionnaire",
                "export_questionnaire",
                "export_questionnaire_preview",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_admin_write_legacy_forward",
            "legacy_questionnaire_facade": "questionnaire_admin_write_legacy_facade",
            "create_questionnaire_in_legacy": "questionnaire_admin_write_legacy_facade",
            "update_questionnaire_in_legacy": "questionnaire_admin_write_legacy_facade",
            "delete_questionnaire_in_legacy": "questionnaire_admin_write_legacy_facade",
            "set_questionnaire_enabled_in_legacy": "questionnaire_admin_write_legacy_facade",
            "export_questionnaire_from_legacy": "questionnaire_admin_write_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_admin_write_compatibility_facade",
            '"fallback_used": True': "questionnaire_admin_write_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_write_fallback_used_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire admin write handlers must execute Next CommandBus commands without legacy forward or compatibility facade behavior.",
                        )
                    )

    write_root = root / "aicrm_next/questionnaire"
    for path in [write_root / "admin_write.py", api_path]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        forbidden_markers = {
            '"fallback_used": True': "questionnaire_admin_write_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_write_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_admin_write_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_admin_write_real_external_call_true",
            "real_enabled": "questionnaire_admin_write_real_enabled_marker",
            "requests.post(": "questionnaire_admin_write_direct_external_call",
            "httpx.post(": "questionnaire_admin_write_direct_external_call",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(path.relative_to(root)),
                        marker,
                        "Questionnaire admin write commands must not expose fallback_used=true, real external calls, or real-enabled adapter behavior.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    write_family = registry_by_path.get("/api/admin/questionnaires*")
    if write_family is None:
        violations.append(Violation("questionnaire_admin_write_registry_family_missing", "docs/architecture/legacy_exit_route_registry.yaml", "/api/admin/questionnaires*"))
    else:
        if write_family.get("runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_admin_write_registry_owner", "/api/admin/questionnaires*", f"runtime_owner={write_family.get('runtime_owner')}"))
        if write_family.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_write_registry_legacy_allowed", "/api/admin/questionnaires*", f"legacy_fallback_allowed={write_family.get('legacy_fallback_allowed')}"))
        if write_family.get("legacy_source"):
            violations.append(Violation("questionnaire_admin_write_registry_legacy_source", "/api/admin/questionnaires*", f"legacy_source={write_family.get('legacy_source')}"))
        if write_family.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_admin_write_registry_adapter_mode", "/api/admin/questionnaires*", f"adapter_mode={write_family.get('adapter_mode')}"))
        if write_family.get("delete_status") != "deletion_locked":
            violations.append(Violation("questionnaire_admin_write_registry_delete_status", "/api/admin/questionnaires*", f"delete_status={write_family.get('delete_status')}"))
        if write_family.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_write_registry_replacement_status", "/api/admin/questionnaires*", f"replacement_status={write_family.get('replacement_status')}"))
        notes = str(write_family.get("notes") or "")
        if "CommandBus" not in notes or "legacy rollback removed" not in notes:
            violations.append(Violation("questionnaire_admin_write_registry_notes", "/api/admin/questionnaires*", notes))

    export_record = registry_by_path.get("/api/admin/questionnaires/{questionnaire_id}/export")
    if export_record is None:
        violations.append(Violation("questionnaire_admin_export_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "/api/admin/questionnaires/{questionnaire_id}/export"))
    elif (
        export_record.get("runtime_owner") != "next_command"
        or export_record.get("legacy_fallback_allowed") is not False
        or export_record.get("adapter_mode") != "real_blocked"
        or export_record.get("delete_status") != "deletion_locked"
        or export_record.get("replacement_status") != "locked"
    ):
        violations.append(
            Violation(
                "questionnaire_admin_export_registry_lifecycle",
                "/api/admin/questionnaires/{questionnaire_id}/export",
                f"runtime_owner={export_record.get('runtime_owner')} legacy_fallback_allowed={export_record.get('legacy_fallback_allowed')} adapter_mode={export_record.get('adapter_mode')} delete_status={export_record.get('delete_status')} replacement_status={export_record.get('replacement_status')}",
            )
        )

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in ["/api/admin/questionnaires*", "/api/admin/questionnaires/{questionnaire_id}/export"]:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_admin_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_admin_write_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("questionnaire_admin_write_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_write_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_admin_write_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_write_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_questionnaire_h5_submit_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in QUESTIONNAIRE_H5_COMMAND_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_h5_submit_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire H5 submit/diagnostics are deletion_locked to Next CommandBus; do not re-add production_compat exact handlers.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    if api_path.exists():
        sources = _function_sources(
            api_path,
            {
                "public_submit_questionnaire",
                "public_questionnaire_client_diagnostics",
                "_execute_h5_submit",
                "_execute_h5_diagnostics",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_h5_submit_legacy_forward",
            "legacy_questionnaire_facade": "questionnaire_h5_submit_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_h5_submit_compatibility_facade",
            '"fallback_used": True': "questionnaire_h5_submit_fallback_used_true",
            "'fallback_used': True": "questionnaire_h5_submit_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_h5_submit_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_h5_submit_real_external_call_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire H5 submit/diagnostics handlers must execute Next CommandBus commands without legacy forward, compatibility facade, fallback_used=true, or real external calls.",
                        )
                    )

    for path in [root / "aicrm_next/questionnaire/h5_write.py", api_path]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        forbidden_markers = {
            '"fallback_used": True': "questionnaire_h5_submit_fallback_used_true",
            "'fallback_used': True": "questionnaire_h5_submit_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_h5_submit_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_h5_submit_real_external_call_true",
            "send_private_message(": "questionnaire_h5_submit_direct_wecom_mutation",
            "dispatch_wecom_task(": "questionnaire_h5_submit_direct_wecom_mutation",
            "mark_contact_tags(": "questionnaire_h5_submit_direct_wecom_mutation",
            "external_push_delivery": "questionnaire_h5_submit_external_push_execution",
            "execute_external_push": "questionnaire_h5_submit_external_push_execution",
            "requests.post(": "questionnaire_h5_submit_direct_external_call",
            "httpx.post(": "questionnaire_h5_submit_direct_external_call",
            "X-AICRM-Compatibility-Facade": "questionnaire_h5_submit_compatibility_facade",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(path.relative_to(root)),
                        marker,
                        "Questionnaire H5 submit/diagnostics must stay on the Next CommandBus with no compatibility facade or direct API-layer external calls.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in QUESTIONNAIRE_H5_COMMAND_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_h5_submit_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_h5_submit_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_h5_submit_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") in {"production_compat", "legacy_questionnaire_facade"}:
            violations.append(Violation("questionnaire_h5_submit_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
        expected_adapter_mode = "real_enabled" if route_path == "/api/h5/questionnaires/{slug}/submit" else "real_blocked"
        if record.get("adapter_mode") != expected_adapter_mode:
            violations.append(Violation("questionnaire_h5_submit_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_h5_submit_registry_rollback_lifecycle", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("questionnaire_h5_submit_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_h5_submit_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))
        notes = str(record.get("notes") or "")
        if "CommandBus" not in notes or "legacy rollback removed" not in notes:
            violations.append(Violation("questionnaire_h5_submit_registry_notes", route_path, notes))
        elif route_path == "/api/h5/questionnaires/{slug}/submit" and "configured questionnaire external push executes" not in notes:
            violations.append(Violation("questionnaire_h5_submit_registry_notes", route_path, notes))
        elif route_path != "/api/h5/questionnaires/{slug}/submit" and "real_external_call_executed=false" not in notes:
            violations.append(Violation("questionnaire_h5_submit_registry_notes", route_path, notes))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in QUESTIONNAIRE_H5_COMMAND_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_h5_submit_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_h5_submit_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("questionnaire_h5_submit_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_h5_submit_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True:
            violations.append(Violation("questionnaire_h5_submit_manifest_not_delete_ready", route_path, f"delete_ready={record.get('delete_ready')}"))
        expected_adapter_mode = "real_enabled" if route_path == "/api/h5/questionnaires/{slug}/submit" else "real_blocked"
        if record.get("adapter_mode") != expected_adapter_mode:
            violations.append(Violation("questionnaire_h5_submit_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_h5_submit_manifest_rollback_lifecycle", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_h5_submit_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_questionnaire_oauth_next_adapter(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_oauth_production_compat_exact_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire OAuth start/callback exact routes must stay Next adapter primary; keep only wildcard/out-of-scope legacy rollback.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    oauth_path = root / "aicrm_next/questionnaire/oauth.py"
    if api_path.exists():
        sources = _function_sources(api_path, {"wechat_oauth_start", "wechat_oauth_callback", "wechat_oauth_start_options", "wechat_oauth_callback_options"})
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_oauth_legacy_forward",
            "X-AICRM-Compatibility-Facade": "questionnaire_oauth_compatibility_facade",
            '"fallback_used": True': "questionnaire_oauth_fallback_used_true",
            "'fallback_used': True": "questionnaire_oauth_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_oauth_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_oauth_real_external_call_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(Violation(code, str(api_path.relative_to(root)), f"{function_name}:{marker}"))

    if oauth_path.exists():
        text = oauth_path.read_text(encoding="utf-8")
        forbidden_markers = {
            "requests.post(": "questionnaire_oauth_direct_external_call",
            "httpx.post(": "questionnaire_oauth_direct_external_call",
            "access_token\":": "questionnaire_oauth_token_leak_marker",
            "app_secret\":": "questionnaire_oauth_token_leak_marker",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(Violation(code, str(oauth_path.relative_to(root)), marker))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_oauth_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != "next_adapter":
            violations.append(Violation("questionnaire_oauth_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not True:
            violations.append(Violation("questionnaire_oauth_registry_legacy_not_retained", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_oauth_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "next_primary_with_legacy_rollback" or record.get("replacement_status") != "validating":
            violations.append(Violation("questionnaire_oauth_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_oauth_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_adapter":
            violations.append(Violation("questionnaire_oauth_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "production_compat"}:
            violations.append(Violation("questionnaire_oauth_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not True:
            violations.append(Violation("questionnaire_oauth_manifest_legacy_not_retained", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_oauth_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "next_primary_with_legacy_rollback" or record.get("replacement_status") != "validating":
            violations.append(Violation("questionnaire_oauth_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def run_checks(*, strict: bool) -> dict:
    violations = (
        scan_source_tree(ROOT)
        + check_customer_read_model_legacy_deletion(ROOT)
        + check_production_compat_routes(ROOT)
        + check_messages_broad_wildcard_deletion(ROOT)
        + check_sidebar_readonly_closeout_lock(ROOT)
        + check_user_ops_next_native_preview(ROOT)
        + check_questionnaire_admin_read_next_native(ROOT)
        + check_questionnaire_admin_write_next_commandbus(ROOT)
        + check_questionnaire_h5_submit_next_commandbus(ROOT)
        + check_questionnaire_oauth_next_adapter(ROOT)
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
