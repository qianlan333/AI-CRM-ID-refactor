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
SIDEBAR_JSSDK_METHODS = ("GET", "HEAD", "OPTIONS")
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
AUTH_WECOM_EXACT_ROUTES = (
    "/auth/wecom/start",
    "/auth/wecom/callback",
    "/auth/wecom/unknown",
    "/api/h5/wechat/oauth/unknown",
)
AUTH_WECOM_WILDCARD_ROUTES = (
    "/api/h5/wechat/oauth/{path:path}",
    "/auth/wecom/{path:path}",
)
AUTH_WECOM_WILDCARD_REGISTRY_ROUTES = (
    "/api/h5/wechat/oauth*",
    "/auth/wecom*",
)
WECOM_TAG_READ_ROUTES = (
    "/api/admin/wecom/tags",
    "/api/admin/wecom/tags/{tag_id}",
    "/api/admin/wecom/tag-groups",
    "/api/admin/wecom/tag-groups/{group_id}",
)
WECOM_TAG_FAMILY_ROUTES = (
    "/api/admin/wecom/tags*",
    "/api/admin/wecom/tag-groups*",
)
WECOM_TAG_WRITE_ROUTES = (
    ("/api/admin/wecom/tags", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tags/{tag_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
    ("/api/admin/wecom/tags/sync", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tags/sync-due", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tag-groups", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tag-groups/{group_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
)
WECOM_TAG_LIVE_MUTATION_ROUTES = (
    ("/api/admin/wecom/tags/live/gate", ("GET",), "next_native", "next_exact"),
    ("/api/admin/wecom/tags/live/mark", ("POST", "OPTIONS"), "next_command", "next_command"),
    ("/api/admin/wecom/tags/live/unmark", ("POST", "OPTIONS"), "next_command", "next_command"),
)
WECOM_TAG_LIVE_MUTATION_EXACT_ROUTES = {route for route, _methods, _owner, _behavior in WECOM_TAG_LIVE_MUTATION_ROUTES}
MEDIA_LIBRARY_PAGE_ROUTES = (
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
)
MEDIA_LIBRARY_API_PREFIXES = (
    "/api/admin/image-library",
    "/api/admin/attachment-library",
    "/api/admin/miniprogram-library",
)
MEDIA_LIBRARY_REGISTRY_FAMILIES = (
    ("media_library_admin_pages_family", "/admin/*-library", ("GET",), "frontend_compat over Next APIs", "none"),
    ("media_library_image_read_family", "/api/admin/image-library*", ("GET",), "next_native", "local"),
    ("media_library_image_command_family", "/api/admin/image-library*", ("POST", "PUT", "DELETE", "OPTIONS"), "next_storage_adapter", "local / fake / real_blocked"),
    ("media_library_attachment_read_family", "/api/admin/attachment-library*", ("GET",), "next_native", "local"),
    ("media_library_attachment_command_family", "/api/admin/attachment-library*", ("POST", "PUT", "DELETE", "OPTIONS"), "next_storage_adapter", "local / fake / real_blocked"),
    ("media_library_miniprogram_read_family", "/api/admin/miniprogram-library*", ("GET",), "next_native", "local"),
    ("media_library_miniprogram_command_family", "/api/admin/miniprogram-library*", ("POST", "PUT", "DELETE", "OPTIONS"), "next_storage_adapter", "local / fake / real_blocked"),
)
MEDIA_LIBRARY_MANIFEST_ROUTES = (
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
    "/api/admin/image-library*",
    "/api/admin/image-library/upload",
    "/api/admin/attachment-library*",
    "/api/admin/miniprogram-library*",
)
MEDIA_LIBRARY_DIRECT_EXTERNAL_MARKERS = {
    "requests.get(": "media_library_direct_http_client",
    "requests.post(": "media_library_direct_http_client",
    "httpx.": "media_library_direct_http_client",
    "boto3": "media_library_direct_storage_client",
    "upload_media": "media_library_direct_wecom_media_upload",
    "/media/upload": "media_library_direct_wecom_media_upload",
    "access_token": "media_library_direct_wecom_media_upload",
    "real_external_call_executed=True": "media_library_real_external_call_true",
    "real_external_call_executed = True": "media_library_real_external_call_true",
    '"real_external_call_executed": True': "media_library_real_external_call_true",
    "'real_external_call_executed': True": "media_library_real_external_call_true",
    "real_enabled default": "media_library_real_enabled_default",
    "default real_enabled": "media_library_real_enabled_default",
}
CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE = "/api/admin/cloud-orchestrator/media/upload"
CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE = "/admin/cloud-orchestrator/campaigns"
CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE = "/api/admin/cloud-orchestrator/campaigns*"
CLOUD_ORCHESTRATOR_CAMPAIGN_READ_SAMPLES = (
    "/api/admin/cloud-orchestrator/campaigns",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps",
)
CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE", "OPTIONS")
CLOUD_ORCHESTRATOR_CAMPAIGN_DIRECT_EXTERNAL_MARKERS = {
    "WeComClient.from_app": "cloud_campaign_read_wecom_client",
    "send_message": "cloud_campaign_read_send_message",
    "dispatch_wecom_task": "cloud_campaign_read_dispatch_wecom_task",
    "process_due_campaign_members": "cloud_campaign_read_runtime",
    "run_due": "cloud_campaign_read_runtime",
    "requests.": "cloud_campaign_read_direct_http_client",
    "httpx": "cloud_campaign_read_direct_http_client",
    "access_token": "cloud_campaign_read_access_token",
    "real_external_call_executed=True": "cloud_campaign_read_real_external_call_true",
    "real_external_call_executed = True": "cloud_campaign_read_real_external_call_true",
    '"real_external_call_executed": True': "cloud_campaign_read_real_external_call_true",
    "'real_external_call_executed': True": "cloud_campaign_read_real_external_call_true",
    "automation_runtime=True": "cloud_campaign_read_runtime_true",
    "automation_runtime = True": "cloud_campaign_read_runtime_true",
    "wecom_send=True": "cloud_campaign_read_wecom_send_true",
    "wecom_send = True": "cloud_campaign_read_wecom_send_true",
}
CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_DIRECT_EXTERNAL_MARKERS = {
    "WeComClient.from_app": "cloud_media_upload_wecom_client",
    "_upload_private_message_image": "cloud_media_upload_private_image_upload",
    "upload_cloud_orchestrator_image": "cloud_media_upload_legacy_helper",
    "access_token": "cloud_media_upload_access_token",
    "requests.": "cloud_media_upload_direct_http_client",
    "httpx": "cloud_media_upload_direct_http_client",
    "real_external_call_executed=True": "cloud_media_upload_real_external_call_true",
    "real_external_call_executed = True": "cloud_media_upload_real_external_call_true",
    '"real_external_call_executed": True': "cloud_media_upload_real_external_call_true",
    "'real_external_call_executed': True": "cloud_media_upload_real_external_call_true",
    "wecom_media_upload_executed=True": "cloud_media_upload_wecom_upload_true",
    "wecom_media_upload_executed = True": "cloud_media_upload_wecom_upload_true",
    '"wecom_media_upload_executed": True': "cloud_media_upload_wecom_upload_true",
    "'wecom_media_upload_executed': True": "cloud_media_upload_wecom_upload_true",
    "real_enabled default": "cloud_media_upload_real_enabled_default",
    "default real_enabled": "cloud_media_upload_real_enabled_default",
}


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


def _module_list_constants(tree: ast.AST) -> dict[str, tuple[str, ...]]:
    constants: dict[str, tuple[str, ...]] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        values: list[str] = []
        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value.upper())
        if values:
            constants[node.targets[0].id] = tuple(values)
    return constants


def _decorator_route_methods(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = _module_list_constants(tree)
    route_methods: list[tuple[str, tuple[str, ...]]] = []
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
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            methods: tuple[str, ...] = ("GET",)
            for keyword in decorator.keywords:
                if keyword.arg != "methods":
                    continue
                if isinstance(keyword.value, (ast.List, ast.Tuple)):
                    parsed = [
                        str(item.value).upper()
                        for item in keyword.value.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    ]
                    methods = tuple(parsed)
                elif isinstance(keyword.value, ast.Name):
                    methods = constants.get(keyword.value.id, methods)
            route_methods.append((first.value, methods))
    return route_methods


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
    for route_path, methods in _decorator_route_methods(compat_path):
        registry_lookup_path = {
            "/api/admin/wecom/tags": "/api/admin/wecom/tags*",
            "/api/admin/wecom/tag-groups": "/api/admin/wecom/tag-groups*",
        }.get(route_path, route_path)
        entry = service.find_route(registry_lookup_path, set(methods))
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
        if (
            jssdk_record.get("production_behavior") != "next_adapter"
            or jssdk_record.get("delete_ready") is not True
            or jssdk_record.get("legacy_fallback_allowed") is not False
        ):
            violations.append(
                Violation(
                    "sidebar_jssdk_not_locked_by_group15_closeout",
                    SIDEBAR_JSSDK_ROUTE,
                    f"production_behavior={jssdk_record.get('production_behavior')} delete_ready={jssdk_record.get('delete_ready')} legacy_fallback_allowed={jssdk_record.get('legacy_fallback_allowed')}",
                    "Sidebar JSSDK group 15 is deletion_locked on the Next adapter; production_compat rollback must not be restored.",
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


def check_sidebar_jssdk_next_adapter(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path in _decorator_route_paths(compat_path):
            if route_path == SIDEBAR_JSSDK_ROUTE:
                violations.append(
                    Violation(
                        "sidebar_jssdk_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Remove /api/sidebar/jssdk-config from production_compat; the route is deletion_locked on the Next JSSDK adapter.",
                    )
                )

    inventory_path = root / "docs/architecture/sidebar_jssdk_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("sidebar_jssdk_inventory_missing", str(inventory_path.relative_to(root)), "missing inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend ↔ API ↔ Backend Contract Matrix",
            "/sidebar/bind-mobile",
            "sidebar_customer_workbench.html",
            "sidebar_workbench.js",
            "/api/sidebar/jssdk-config",
            "url",
            "debug",
            "agentid",
            "ok",
            "appId",
            "corpId",
            "timestamp",
            "nonceStr",
            "signature",
            "jsApiList",
            "source_status",
            "adapter_mode",
            "route_owner",
            "fallback_used",
            "real_external_call_executed",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("sidebar_jssdk_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/identity_contact/sidebar_jssdk.py"
    adapter_path = root / "aicrm_next/integration_gateway/wecom_jssdk_adapter.py"
    main_path = root / "aicrm_next/main.py"
    for path, markers in [
        (api_path, ("sidebar_jssdk_config", "build_sidebar_jssdk_config", "HEAD", "OPTIONS")),
        (adapter_path, ("build_sidebar_jssdk_config", "ExternalCallAttempt", "record_event", "real_external_call_executed")),
    ]:
        if not path.exists():
            violations.append(Violation("sidebar_jssdk_module_missing", str(path.relative_to(root)), ",".join(markers)))
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in source:
                violations.append(Violation("sidebar_jssdk_module_marker_missing", str(path.relative_to(root)), marker))
        for forbidden, code in {
            "forward_to_legacy_flask": "sidebar_jssdk_legacy_forward",
            "legacy_flask_facade": "sidebar_jssdk_legacy_facade",
            "production_compat": "sidebar_jssdk_production_compat_reference",
            "X-AICRM-Compatibility-Facade": "sidebar_jssdk_compatibility_facade",
            "requests.": "sidebar_jssdk_direct_http_client",
            "requests": "sidebar_jssdk_direct_http_client",
            "httpx.": "sidebar_jssdk_direct_http_client",
            "httpx": "sidebar_jssdk_direct_http_client",
            '"fallback_used": True': "sidebar_jssdk_fallback_used_true",
            "'fallback_used': True": "sidebar_jssdk_fallback_used_true",
        }.items():
            if forbidden in source:
                violations.append(Violation(code, str(path.relative_to(root)), forbidden))
        normalized = " ".join(source.lower().split())
        for marker in ("default real_enabled", "real_enabled default", "return 'real_enabled' # default", 'return "real_enabled" # default'):
            if marker in normalized:
                violations.append(
                    Violation(
                        "sidebar_jssdk_default_real_enabled",
                        str(path.relative_to(root)),
                        marker,
                        "Sidebar JSSDK production default must stay real_blocked; real signing requires the explicit real_enabled gate.",
                    )
                )

    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        if "sidebar_jssdk_router" not in main_text:
            violations.append(Violation("sidebar_jssdk_router_not_included", str(main_path.relative_to(root)), "sidebar_jssdk_router"))
        elif "production_compat_router" in main_text and main_text.index("sidebar_jssdk_router") > main_text.index("production_compat_router"):
            violations.append(
                Violation(
                    "sidebar_jssdk_router_order",
                    str(main_path.relative_to(root)),
                    "sidebar_jssdk_router must be included before production_compat_router",
                )
            )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_route = {(record.get("path_pattern"), tuple(record.get("methods") or [])): record for record in registry_records}
    registry_record = registry_by_route.get((SIDEBAR_JSSDK_ROUTE, ("GET", "HEAD", "OPTIONS")))
    if registry_record is None:
        violations.append(Violation("sidebar_jssdk_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", SIDEBAR_JSSDK_ROUTE))
    else:
        if registry_record.get("runtime_owner") != "next_adapter":
            violations.append(Violation("sidebar_jssdk_registry_owner", SIDEBAR_JSSDK_ROUTE, f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_jssdk_registry_legacy_allowed", SIDEBAR_JSSDK_ROUTE, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
        if registry_record.get("legacy_source") == "production_compat":
            violations.append(Violation("sidebar_jssdk_registry_legacy_source", SIDEBAR_JSSDK_ROUTE, "legacy_source=production_compat"))
        if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
            violations.append(Violation("sidebar_jssdk_registry_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))
        if registry_record.get("delete_status") == "next_primary_with_legacy_rollback" or registry_record.get("replacement_status") == "validating":
            violations.append(Violation("sidebar_jssdk_registry_rollback_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))
        if registry_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("sidebar_jssdk_registry_adapter_mode", SIDEBAR_JSSDK_ROUTE, f"adapter_mode={registry_record.get('adapter_mode')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_route = {(record.get("route_pattern"), tuple(record.get("methods") or [])): record for record in manifest_records}
    manifest_record = manifest_by_route.get((SIDEBAR_JSSDK_ROUTE, ("GET", "HEAD", "OPTIONS")))
    if manifest_record is None:
        violations.append(Violation("sidebar_jssdk_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", SIDEBAR_JSSDK_ROUTE))
    else:
        if manifest_record.get("current_runtime_owner") != "next_adapter":
            violations.append(Violation("sidebar_jssdk_manifest_owner", SIDEBAR_JSSDK_ROUTE, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("production_behavior") != "next_adapter":
            violations.append(Violation("sidebar_jssdk_manifest_behavior", SIDEBAR_JSSDK_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("sidebar_jssdk_manifest_legacy_forward", SIDEBAR_JSSDK_ROUTE, "production_behavior=legacy_forward"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_jssdk_manifest_legacy_allowed", SIDEBAR_JSSDK_ROUTE, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("delete_ready") is not True:
            violations.append(Violation("sidebar_jssdk_manifest_delete_ready", SIDEBAR_JSSDK_ROUTE, f"delete_ready={manifest_record.get('delete_ready')}"))
        if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
            violations.append(Violation("sidebar_jssdk_manifest_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
        if manifest_record.get("delete_status") == "next_primary_with_legacy_rollback" or manifest_record.get("replacement_status") == "validating":
            violations.append(Violation("sidebar_jssdk_manifest_rollback_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
        if manifest_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("sidebar_jssdk_manifest_adapter_mode", SIDEBAR_JSSDK_ROUTE, f"adapter_mode={manifest_record.get('adapter_mode')}"))

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
        if write_family.get("legacy_fallback_allowed") is not True:
            violations.append(Violation("questionnaire_admin_write_registry_legacy_allowed", "/api/admin/questionnaires*", f"legacy_fallback_allowed={write_family.get('legacy_fallback_allowed')}"))
        if write_family.get("legacy_source") != "legacy_flask_facade":
            violations.append(Violation("questionnaire_admin_write_registry_legacy_source", "/api/admin/questionnaires*", f"legacy_source={write_family.get('legacy_source')}"))
        if write_family.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_admin_write_registry_adapter_mode", "/api/admin/questionnaires*", f"adapter_mode={write_family.get('adapter_mode')}"))
        if write_family.get("delete_status") != "active_fallback":
            violations.append(Violation("questionnaire_admin_write_registry_delete_status", "/api/admin/questionnaires*", f"delete_status={write_family.get('delete_status')}"))
        if write_family.get("replacement_status") != "production_fallback":
            violations.append(Violation("questionnaire_admin_write_registry_replacement_status", "/api/admin/questionnaires*", f"replacement_status={write_family.get('replacement_status')}"))
        notes = str(write_family.get("notes") or "")
        if "CommandBus" not in notes or "legacy_flask_facade" not in notes or "production_data_ready" not in notes:
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
        expected_behavior = "next_command_local_legacy_write_fallback" if route_path == "/api/admin/questionnaires*" else "next_command"
        if record.get("production_behavior") != expected_behavior:
            violations.append(Violation("questionnaire_admin_write_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        expected_fallback = route_path == "/api/admin/questionnaires*"
        if record.get("legacy_fallback_allowed") is not expected_fallback:
            violations.append(Violation("questionnaire_admin_write_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_admin_write_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        expected_delete_status = "active_fallback" if route_path == "/api/admin/questionnaires*" else "deletion_locked"
        expected_replacement_status = "production_fallback" if route_path == "/api/admin/questionnaires*" else "locked"
        if record.get("delete_status") != expected_delete_status or record.get("replacement_status") != expected_replacement_status:
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
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_oauth_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") in {"production_compat", "legacy_questionnaire_facade"}:
            violations.append(Violation("questionnaire_oauth_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_oauth_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("questionnaire_oauth_registry_production_compat_owner", route_path, "runtime_owner=production_compat"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_oauth_registry_rollback_lifecycle", route_path, "delete_status=next_primary_with_legacy_rollback"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
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
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_oauth_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_oauth_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("current_runtime_owner") == "production_compat":
            violations.append(Violation("questionnaire_oauth_manifest_production_compat_owner", route_path, "current_runtime_owner=production_compat"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_oauth_manifest_rollback_lifecycle", route_path, "delete_status=next_primary_with_legacy_rollback"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_oauth_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_auth_wecom_wildcard_inventory(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/auth_wecom_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "auth_wecom_inventory_missing",
                "docs/architecture/auth_wecom_route_inventory.md",
                "missing inventory document",
                "Add docs/architecture/auth_wecom_route_inventory.md before retaining or replacing auth/wecom wildcard routes.",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path in AUTH_WECOM_EXACT_ROUTES + AUTH_WECOM_WILDCARD_ROUTES + QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("auth_wecom_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in AUTH_WECOM_EXACT_ROUTES:
                violations.append(
                    Violation(
                        "auth_wecom_production_compat_exact_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Known auth/wecom and OAuth probe exact routes must stay Next-owned with no production_compat fallback.",
                    )
                )
            if route_path in AUTH_WECOM_WILDCARD_ROUTES:
                violations.append(
                    Violation(
                        "auth_wecom_deleted_wildcard_reintroduced",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Auth/wecom and OAuth wildcard fallbacks are deleted and locked; do not re-add production_compat wildcard decorators.",
                    )
                )
            if (
                (route_path.startswith("/auth/wecom") or route_path.startswith("/api/h5/wechat/oauth"))
                and "{path:path}" in route_path
            ):
                violations.append(
                    Violation(
                        "auth_wecom_unregistered_wildcard",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Do not add new auth/wecom or OAuth wildcard routes; inventory exact paths and register them explicitly.",
                    )
                )

    auth_api_path = root / "aicrm_next/auth_wecom/api.py"
    if auth_api_path.exists():
        text = auth_api_path.read_text(encoding="utf-8")
        forbidden_markers = {
            "forward_to_legacy_flask": "auth_wecom_legacy_forward",
            "legacy_flask_facade": "auth_wecom_legacy_facade",
            "X-AICRM-Compatibility-Facade": "auth_wecom_compatibility_facade",
            '"fallback_used": True': "auth_wecom_fallback_used_true",
            "'fallback_used': True": "auth_wecom_fallback_used_true",
            '"real_external_call_executed": True': "auth_wecom_real_external_call_true",
            "'real_external_call_executed': True": "auth_wecom_real_external_call_true",
            "requests.post(": "auth_wecom_direct_external_call",
            "httpx.post(": "auth_wecom_direct_external_call",
            "exchange_code_for_wecom_user": "auth_wecom_direct_wecom_exchange",
            "build_wecom_qr_login_url": "auth_wecom_direct_wecom_authorize",
            "build_wecom_oauth_login_url": "auth_wecom_direct_wecom_authorize",
            "access_token\":": "auth_wecom_token_leak_marker",
            "app_secret\":": "auth_wecom_token_leak_marker",
            "real_enabled default": "auth_wecom_real_enabled_default",
            "default real_enabled": "auth_wecom_real_enabled_default",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(auth_api_path.relative_to(root)),
                        marker,
                        "Auth/wecom Next exact responses must not forward to legacy, leak tokens, or execute real OAuth/WeCom calls.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}

    for route_path in AUTH_WECOM_EXACT_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("auth_wecom_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if record.get("runtime_owner") != "next_native":
                violations.append(Violation("auth_wecom_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
            if record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
            if record.get("adapter_mode") not in {"real_blocked", "none"}:
                violations.append(Violation("auth_wecom_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
            if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
                violations.append(Violation("auth_wecom_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        manifest_record = manifest_by_path.get(route_path)
        if manifest_record is None:
            violations.append(Violation("auth_wecom_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("auth_wecom_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_exact":
                violations.append(Violation("auth_wecom_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("auth_wecom_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    for route_path in AUTH_WECOM_WILDCARD_REGISTRY_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("auth_wecom_wildcard_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if record.get("runtime_owner") == "production_compat":
                violations.append(Violation("auth_wecom_wildcard_registry_production_compat", route_path, f"runtime_owner={record.get('runtime_owner')}"))
            if record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_wildcard_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
            if record.get("delete_status") == "active" or record.get("replacement_status") == "validating":
                violations.append(Violation("auth_wecom_wildcard_registry_retained_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
            if record.get("delete_status") not in {"legacy_deleted", "deletion_locked"} or record.get("replacement_status") not in {"deleted", "locked"}:
                violations.append(Violation("auth_wecom_wildcard_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        manifest_record = manifest_by_path.get(route_path)
        if manifest_record is None:
            violations.append(Violation("auth_wecom_wildcard_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") == "production_compat":
                violations.append(Violation("auth_wecom_wildcard_manifest_production_compat", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("auth_wecom_wildcard_manifest_legacy_forward", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_wildcard_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("delete_status") == "active" or manifest_record.get("replacement_status") == "validating":
                violations.append(Violation("auth_wecom_wildcard_manifest_retained_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
            if manifest_record.get("delete_status") not in {"legacy_deleted", "deletion_locked"} or manifest_record.get("replacement_status") not in {"deleted", "locked"}:
                violations.append(Violation("auth_wecom_wildcard_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def check_wecom_tag_read_next_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/wecom_tag_read_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "wecom_tag_read_inventory_missing",
                "docs/architecture/wecom_tag_read_route_inventory.md",
                "missing inventory document",
                "Add the WeCom tag read route inventory before moving read routes or changing tag fallback lifecycle.",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path in WECOM_TAG_READ_ROUTES + WECOM_TAG_FAMILY_ROUTES + ("/api/sidebar/signup-tags/status",):
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_read_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for phrase in ("Write Out Of Scope", "External Side Effects Out Of Scope", "No separate sidebar tag catalog selector"):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_read_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/customer_tags/api.py"
    read_model_path = root / "aicrm_next/customer_tags/read_model.py"
    main_path = root / "aicrm_next/main.py"
    production_compat_path = root / "aicrm_next/production_compat/api.py"
    if not api_path.exists():
        violations.append(Violation("wecom_tag_read_api_missing", str(api_path.relative_to(root)), "missing customer_tags api"))
    else:
        api_text = api_path.read_text(encoding="utf-8")
        if "read_router = APIRouter()" not in api_text:
            violations.append(Violation("wecom_tag_read_router_missing", str(api_path.relative_to(root)), "read_router = APIRouter()"))
        for route_path in WECOM_TAG_READ_ROUTES:
            if f'@read_router.get("{route_path}")' not in api_text and f"@read_router.get('{route_path}')" not in api_text:
                violations.append(Violation("wecom_tag_read_exact_route_missing", str(api_path.relative_to(root)), route_path))
        sources = _function_sources(
            api_path,
            {
                "list_admin_wecom_tags_read_model",
                "get_admin_wecom_tag_read_model",
                "list_admin_wecom_tag_groups_read_model",
                "get_admin_wecom_tag_group_read_model",
                "_read_catalog_payload",
                "_production_unavailable",
            },
        )
        for function_name, source in sources.items():
            for marker, code in {
                "forward_to_legacy_flask": "wecom_tag_read_legacy_forward",
                "legacy_flask_facade": "wecom_tag_read_legacy_facade",
                "X-AICRM-Compatibility-Facade": "wecom_tag_read_compatibility_facade",
                '"fallback_used": True': "wecom_tag_read_fallback_used_true",
                "'fallback_used': True": "wecom_tag_read_fallback_used_true",
                '"real_external_call_executed": True': "wecom_tag_read_real_external_call_true",
                "'real_external_call_executed': True": "wecom_tag_read_real_external_call_true",
                '"sync_executed": True': "wecom_tag_read_sync_executed_true",
                "'sync_executed': True": "wecom_tag_read_sync_executed_true",
                "requests.": "wecom_tag_read_direct_http_client",
                "httpx.": "wecom_tag_read_direct_http_client",
                "list_wecom_tags_live": "wecom_tag_read_real_wecom_sync",
                "mark_tags_live": "wecom_tag_read_real_wecom_mutation",
            }.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "WeCom tag read routes must use the Next read model with no legacy forward, compatibility facade, or real WeCom call.",
                        )
                    )
    if not read_model_path.exists():
        violations.append(Violation("wecom_tag_read_model_missing", str(read_model_path.relative_to(root)), "missing tag catalog read model"))
    if read_model_path.exists():
        source = read_model_path.read_text(encoding="utf-8")
        for marker, code in {
            "requests.": "wecom_tag_read_direct_http_client",
            "httpx.": "wecom_tag_read_direct_http_client",
            "WeComTagLiveGateway": "wecom_tag_read_real_wecom_gateway",
            "list_wecom_tags_live": "wecom_tag_read_real_wecom_sync",
            "mark_external_contact_tags": "wecom_tag_read_real_wecom_mutation",
            "production_success_claimed": "wecom_tag_read_production_success_claimed",
        }.items():
            if marker in source:
                violations.append(Violation(code, str(read_model_path.relative_to(root)), marker))
    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        read_include = main_text.find("include_router(customer_tags_read_router)")
        compat_include = main_text.find("include_router(production_compat_router)")
        if read_include < 0 or compat_include < 0 or read_include > compat_include:
            violations.append(
                Violation(
                    "wecom_tag_read_router_order",
                    str(main_path.relative_to(root)),
                    "customer_tags_read_router must be included before production_compat_router",
                )
            )
    if production_compat_path.exists():
        compat_text = production_compat_path.read_text(encoding="utf-8")
        write_methods_line = next(
            (line for line in compat_text.splitlines() if line.strip().startswith("_WRITE_FALLBACK_METHODS")),
            "",
        )
        if "GET" in write_methods_line or "HEAD" in write_methods_line:
            violations.append(
                Violation(
                    "wecom_tag_read_production_compat_write_methods_include_read",
                    str(production_compat_path.relative_to(root)),
                    write_methods_line.strip(),
                    "Keep WeCom tag production_compat fallback limited to write/sync methods; read routes are locked to Next.",
                )
            )
        for line in compat_text.splitlines():
            if (
                "@router.api_route(" in line
                and (
                    '"/api/admin/wecom/tags' in line
                    or "'/api/admin/wecom/tags" in line
                    or '"/api/admin/wecom/tag-groups' in line
                    or "'/api/admin/wecom/tag-groups" in line
                )
                and ("_ALL_METHODS" in line or '"GET"' in line or "'GET'" in line or '"HEAD"' in line or "'HEAD'" in line)
            ):
                violations.append(
                    Violation(
                        "wecom_tag_read_production_compat_read_route",
                        str(production_compat_path.relative_to(root)),
                        line.strip(),
                        "Do not register WeCom tag read routes in production_compat; keep only write/sync fallback methods.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")

    for route_path in WECOM_TAG_READ_ROUTES:
        record = _record_for_path_and_methods(registry_records, "path_pattern", route_path, ("GET",))
        if record is None:
            violations.append(Violation("wecom_tag_read_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if record.get("runtime_owner") != "next_native":
                violations.append(Violation("wecom_tag_read_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
            if record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_read_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
            if record.get("legacy_source") not in {"", None}:
                violations.append(Violation("wecom_tag_read_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
            if record.get("external_side_effect_risk") != "none":
                violations.append(Violation("wecom_tag_read_registry_side_effect_risk", route_path, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
            if record.get("adapter_mode") not in {"none", ""}:
                violations.append(Violation("wecom_tag_read_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
            if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_read_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        manifest_record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("GET",))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_read_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("wecom_tag_read_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_exact":
                violations.append(Violation("wecom_tag_read_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_read_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("external_side_effect_risk") != "none":
                violations.append(Violation("wecom_tag_read_manifest_side_effect_risk", route_path, f"external_side_effect_risk={manifest_record.get('external_side_effect_risk')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("wecom_tag_read_manifest_behavior", route_path, "production_behavior=legacy_forward"))
            if manifest_record.get("current_runtime_owner") == "production_compat":
                violations.append(Violation("wecom_tag_read_manifest_owner", route_path, "current_runtime_owner=production_compat"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_read_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    for route_path in WECOM_TAG_FAMILY_ROUTES:
        manifest_record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_family_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if manifest_record.get("current_runtime_owner") != "next":
            violations.append(Violation("wecom_tag_family_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("wecom_tag_family_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("wecom_tag_family_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("delete_status") == "deletion_locked" or manifest_record.get("replacement_status") == "locked":
            violations.append(Violation("wecom_tag_family_manifest_mislocked", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def _record_for_path_and_methods(records: list[dict], path_key: str, path: str, methods: tuple[str, ...]) -> dict | None:
    exact = [record for record in records if record.get(path_key) == path and tuple(record.get("methods") or []) == methods]
    if exact:
        return exact[0]
    methodless = [record for record in records if record.get(path_key) == path and not record.get("methods")]
    if methodless:
        return methodless[0]
    return None


def _is_media_library_route_path(route_path: str) -> bool:
    return route_path in MEDIA_LIBRARY_PAGE_ROUTES or any(route_path.startswith(prefix) for prefix in MEDIA_LIBRARY_API_PREFIXES)


def check_media_library_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/media_library_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("media_library_inventory_missing", str(inventory_path.relative_to(root)), "missing Media Library inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend ↔ API ↔ Backend Contract Matrix",
            "production_compat rollback is removed",
            "legacy_fallback_allowed",
            "deletion_locked",
            "real_external_call_executed=false",
            "Real external object storage enablement.",
            "Real WeCom media upload.",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("media_library_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path)) | set(_decorated_route_function_sources(compat_path))
        for route_path in sorted(route_paths):
            if _is_media_library_route_path(route_path):
                violations.append(
                    Violation(
                        "media_library_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Media Library group 16 is deletion_locked to Next/front-end-compat-over-Next APIs; do not register production_compat rollback routes.",
                    )
                )

    media_root = root / "aicrm_next/media_library"
    if media_root.exists():
        for path in media_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            for marker, code in MEDIA_LIBRARY_DIRECT_EXTERNAL_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Media Library closeout must keep real external storage, direct HTTP fetch, and real WeCom media upload blocked by default.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id, path_pattern, methods, owner, adapter_mode in MEDIA_LIBRARY_REGISTRY_FAMILIES:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("media_library_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("path_pattern") != path_pattern or tuple(record.get("methods") or []) != methods:
            violations.append(Violation("media_library_registry_route_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != owner:
            violations.append(Violation("media_library_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("media_library_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("media_library_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("media_library_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("adapter_mode") != adapter_mode:
            violations.append(Violation("media_library_registry_adapter_mode", route_id, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("media_library_registry_rollback_lifecycle", route_id, "delete_status=next_primary_with_legacy_rollback"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in MEDIA_LIBRARY_MANIFEST_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("media_library_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        expected_owner = "frontend_compat" if route_path in MEDIA_LIBRARY_PAGE_ROUTES else "next"
        if record.get("current_runtime_owner") != expected_owner:
            violations.append(Violation("media_library_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("media_library_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True:
            violations.append(Violation("media_library_manifest_delete_ready", route_path, f"delete_ready={record.get('delete_ready')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("media_library_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("media_library_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        notes = str(record.get("notes") or "")
        if route_path.startswith("/api/admin/") and ("real external" not in notes and "cloud storage" not in notes):
            violations.append(Violation("media_library_manifest_no_real_storage_note", route_path, "notes must document no real external storage"))
        if route_path.startswith("/api/admin/") and "WeCom media" not in notes:
            violations.append(Violation("media_library_manifest_no_real_wecom_note", route_path, "notes must document no real WeCom media upload"))

    return violations


def check_cloud_orchestrator_media_upload_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/cloud_orchestrator_media_upload_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "cloud_media_upload_inventory_missing",
                str(inventory_path.relative_to(root)),
                "missing Cloud Orchestrator media upload inventory document",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Deletion Closeout Status Matrix",
            "production_compat rollback removed",
            "Next adapter only",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "real_external_call_executed=false",
            "wecom_media_upload_executed=false",
        ):
            if phrase not in inventory_text:
                violations.append(
                    Violation(
                        "cloud_media_upload_inventory_boundary_missing",
                        str(inventory_path.relative_to(root)),
                        phrase,
                        "Document that Cloud Orchestrator media upload is locked to the Next adapter with production_compat rollback removed.",
                    )
                )

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        compat_text = compat_path.read_text(encoding="utf-8")
        if CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE in compat_text:
            violations.append(
                Violation(
                    "cloud_media_upload_production_compat_route",
                    str(compat_path.relative_to(root)),
                    CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE,
                    "Cloud Orchestrator media upload deletion closeout removed this exact production_compat rollback; campaigns/run-due routes remain out of scope.",
                )
            )
        for route_path in _decorator_route_paths(compat_path):
            if route_path == CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE:
                violations.append(
                    Violation(
                        "cloud_media_upload_production_compat_decorator",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Do not register POST/OPTIONS /api/admin/cloud-orchestrator/media/upload in production_compat.",
                    )
                )

    cloud_root = root / "aicrm_next/cloud_orchestrator"
    if cloud_root.exists():
        for path in cloud_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            for marker, code in CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_DIRECT_EXTERNAL_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Cloud Orchestrator media upload closeout must keep real WeCom media upload and direct HTTP clients blocked by default.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_record = next(
        (record for record in registry_records if record.get("route_id") == "cloud_orchestrator_media_upload_adapter"),
        None,
    )
    if registry_record is None:
        violations.append(
            Violation(
                "cloud_media_upload_registry_missing",
                "docs/architecture/legacy_exit_route_registry.yaml",
                "cloud_orchestrator_media_upload_adapter",
                "Keep the Cloud Orchestrator media upload route registered and deletion_locked.",
            )
        )
    else:
        if registry_record.get("path_pattern") != CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE:
            violations.append(Violation("cloud_media_upload_registry_path", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"path_pattern={registry_record.get('path_pattern')}"))
        if tuple(registry_record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("cloud_media_upload_registry_methods", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"methods={registry_record.get('methods')}"))
        if registry_record.get("runtime_owner") not in {"next_adapter", "next_command"}:
            violations.append(Violation("cloud_media_upload_registry_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("runtime_owner") == "production_compat":
            violations.append(Violation("cloud_media_upload_registry_production_compat_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, "runtime_owner=production_compat"))
        if registry_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_media_upload_registry_legacy_allowed", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
        if registry_record.get("legacy_source") not in {"", None}:
            violations.append(Violation("cloud_media_upload_registry_legacy_source", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"legacy_source={registry_record.get('legacy_source')}"))
        if registry_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
            violations.append(Violation("cloud_media_upload_registry_rollback_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={registry_record.get('delete_status')}"))
        if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_media_upload_registry_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))
        if registry_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("cloud_media_upload_registry_adapter_mode", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"adapter_mode={registry_record.get('adapter_mode')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_record = next((record for record in manifest_records if record.get("route_pattern") == CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE), None)
    if manifest_record is None:
        violations.append(
            Violation(
                "cloud_media_upload_manifest_missing",
                "docs/route_ownership/production_route_ownership_manifest.yaml",
                CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE,
                "Keep the Cloud Orchestrator media upload production manifest record deletion_locked.",
            )
        )
    else:
        if manifest_record.get("current_runtime_owner") not in {"next", "next_adapter", "next_command"}:
            violations.append(Violation("cloud_media_upload_manifest_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("current_runtime_owner") == "production_compat":
            violations.append(Violation("cloud_media_upload_manifest_production_compat_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, "current_runtime_owner=production_compat"))
        if manifest_record.get("production_behavior") != "next_adapter":
            violations.append(Violation("cloud_media_upload_manifest_behavior", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("cloud_media_upload_manifest_legacy_behavior", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_media_upload_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("delete_ready") is not True:
            violations.append(Violation("cloud_media_upload_manifest_delete_ready", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_ready={manifest_record.get('delete_ready')}"))
        if manifest_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
            violations.append(Violation("cloud_media_upload_manifest_rollback_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={manifest_record.get('delete_status')}"))
        if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_media_upload_manifest_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
        if manifest_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("cloud_media_upload_manifest_adapter_mode", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"adapter_mode={manifest_record.get('adapter_mode')}"))

    return violations


def check_cloud_orchestrator_campaign_read_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/cloud_orchestrator_campaigns_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "cloud_campaign_read_inventory_missing",
                str(inventory_path.relative_to(root)),
                "missing Cloud Orchestrator campaigns route inventory document",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Deletion Closeout Status Matrix",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "legacy fallback removed",
            "write controls disabled/out-of-scope",
            "No real WeCom send",
            "No automation runtime",
        ):
            if phrase not in inventory_text:
                violations.append(
                    Violation(
                        "cloud_campaign_read_inventory_boundary_missing",
                        str(inventory_path.relative_to(root)),
                        phrase,
                        "Document that campaign read/workspace routes are locked to Next and write/run-due remain out of scope.",
                    )
                )
        for route_path in CLOUD_ORCHESTRATOR_CAMPAIGN_READ_SAMPLES:
            if route_path not in inventory_text:
                violations.append(
                    Violation(
                        "cloud_campaign_read_inventory_route_missing",
                        str(inventory_path.relative_to(root)),
                        route_path,
                    )
                )

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, methods in _decorator_route_methods(compat_path):
            if route_path in {
                "/api/admin/cloud-orchestrator/campaigns",
                "/api/admin/cloud-orchestrator/campaigns/{path:path}",
            } and "GET" in set(methods):
                violations.append(
                    Violation(
                        "cloud_campaign_read_production_compat_get_route",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={methods}",
                        "Campaign GET read rollback is deletion_locked; production_compat may retain only write/run-due methods.",
                    )
                )

    read_model_path = root / "aicrm_next/cloud_orchestrator/campaigns_read.py"
    if read_model_path.exists():
        text = read_model_path.read_text(encoding="utf-8")
        rel = str(read_model_path.relative_to(root))
        for marker, code in CLOUD_ORCHESTRATOR_CAMPAIGN_DIRECT_EXTERNAL_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Campaign read closeout must not trigger real WeCom send, automation runtime, token exchange, or direct HTTP calls.",
                    )
                )

    api_path = root / "aicrm_next/cloud_orchestrator/api.py"
    if api_path.exists():
        api_text = api_path.read_text(encoding="utf-8")
        rel = str(api_path.relative_to(root))
        for marker in (
            "X-AICRM-Compatibility-Facade",
            '"fallback_used": True',
            "'fallback_used': True",
            "fallback_used=True",
            "real_external_call_executed=True",
            "real_external_call_executed = True",
            '"real_external_call_executed": True',
            "'real_external_call_executed': True",
        ):
            if marker in api_text:
                violations.append(
                    Violation(
                        "cloud_campaign_read_response_contract_drift",
                        rel,
                        marker,
                        "Campaign read API must return fallback_used=false, no compatibility facade, and no real_external_call_executed=true.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    read_record = registry_by_id.get("cloud_orchestrator_campaigns_read_family")
    if read_record is None:
        violations.append(Violation("cloud_campaign_read_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_read_family"))
    else:
        if read_record.get("path_pattern") != CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE or tuple(read_record.get("methods") or []) != ("GET",):
            violations.append(Violation("cloud_campaign_read_registry_route_shape", "cloud_orchestrator_campaigns_read_family", f"path_pattern={read_record.get('path_pattern')} methods={read_record.get('methods')}"))
        if read_record.get("runtime_owner") != "next_read_model":
            violations.append(Violation("cloud_campaign_read_registry_owner", "cloud_orchestrator_campaigns_read_family", f"runtime_owner={read_record.get('runtime_owner')}"))
        if read_record.get("runtime_owner") == "production_compat":
            violations.append(Violation("cloud_campaign_read_registry_production_compat_owner", "cloud_orchestrator_campaigns_read_family", "runtime_owner=production_compat"))
        if read_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_read_registry_legacy_allowed", "cloud_orchestrator_campaigns_read_family", f"legacy_fallback_allowed={read_record.get('legacy_fallback_allowed')}"))
        if read_record.get("legacy_source") not in {"", None}:
            violations.append(Violation("cloud_campaign_read_registry_legacy_source", "cloud_orchestrator_campaigns_read_family", f"legacy_source={read_record.get('legacy_source')}"))
        if read_record.get("external_side_effect_risk") != "none":
            violations.append(Violation("cloud_campaign_read_registry_side_effect_risk", "cloud_orchestrator_campaigns_read_family", f"external_side_effect_risk={read_record.get('external_side_effect_risk')}"))
        if read_record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("cloud_campaign_read_registry_rollback_lifecycle", "cloud_orchestrator_campaigns_read_family", "delete_status=next_primary_with_legacy_rollback"))
        if read_record.get("delete_status") != "deletion_locked" or read_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_read_registry_lifecycle", "cloud_orchestrator_campaigns_read_family", f"delete_status={read_record.get('delete_status')} replacement_status={read_record.get('replacement_status')}"))

    page_record = registry_by_id.get("cloud_orchestrator_campaigns_page")
    if page_record is None:
        violations.append(Violation("cloud_campaign_page_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_page"))
    else:
        if page_record.get("path_pattern") != CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE or tuple(page_record.get("methods") or []) != ("GET",):
            violations.append(Violation("cloud_campaign_page_registry_route_shape", "cloud_orchestrator_campaigns_page", f"path_pattern={page_record.get('path_pattern')} methods={page_record.get('methods')}"))
        if page_record.get("runtime_owner") != "frontend_compat over Next read APIs":
            violations.append(Violation("cloud_campaign_page_registry_owner", "cloud_orchestrator_campaigns_page", f"runtime_owner={page_record.get('runtime_owner')}"))
        if page_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_page_registry_legacy_allowed", "cloud_orchestrator_campaigns_page", f"legacy_fallback_allowed={page_record.get('legacy_fallback_allowed')}"))
        if page_record.get("delete_status") != "deletion_locked" or page_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_page_registry_lifecycle", "cloud_orchestrator_campaigns_page", f"delete_status={page_record.get('delete_status')} replacement_status={page_record.get('replacement_status')}"))

    write_record = registry_by_id.get("cloud_orchestrator_campaigns_write_legacy_family")
    if write_record is None:
        violations.append(Violation("cloud_campaign_write_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_write_legacy_family"))
    else:
        if write_record.get("runtime_owner") != "production_compat":
            violations.append(Violation("cloud_campaign_write_registry_owner", "cloud_orchestrator_campaigns_write_legacy_family", f"runtime_owner={write_record.get('runtime_owner')}"))
        if write_record.get("delete_status") == "deletion_locked" or write_record.get("replacement_status") == "locked":
            violations.append(Violation("cloud_campaign_write_registry_mislocked", "cloud_orchestrator_campaigns_write_legacy_family", f"delete_status={write_record.get('delete_status')} replacement_status={write_record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    read_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, ("GET",))
    if read_manifest is None:
        violations.append(Violation("cloud_campaign_read_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE))
    else:
        if read_manifest.get("current_runtime_owner") != "next":
            violations.append(Violation("cloud_campaign_read_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"current_runtime_owner={read_manifest.get('current_runtime_owner')}"))
        if read_manifest.get("production_behavior") != "next_exact":
            violations.append(Violation("cloud_campaign_read_manifest_behavior", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"production_behavior={read_manifest.get('production_behavior')}"))
        if read_manifest.get("production_behavior") == "legacy_forward":
            violations.append(Violation("cloud_campaign_read_manifest_legacy_forward", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, "production_behavior=legacy_forward"))
        if read_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_read_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"legacy_fallback_allowed={read_manifest.get('legacy_fallback_allowed')}"))
        if read_manifest.get("external_side_effect_risk") != "none":
            violations.append(Violation("cloud_campaign_read_manifest_side_effect_risk", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"external_side_effect_risk={read_manifest.get('external_side_effect_risk')}"))
        if read_manifest.get("delete_ready") is not True:
            violations.append(Violation("cloud_campaign_read_manifest_delete_ready", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"delete_ready={read_manifest.get('delete_ready')}"))
        if read_manifest.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("cloud_campaign_read_manifest_rollback_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, "delete_status=next_primary_with_legacy_rollback"))
        if read_manifest.get("delete_status") != "deletion_locked" or read_manifest.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_read_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"delete_status={read_manifest.get('delete_status')} replacement_status={read_manifest.get('replacement_status')}"))

    page_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, ("GET",))
    if page_manifest is None:
        violations.append(Violation("cloud_campaign_page_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE))
    else:
        if page_manifest.get("current_runtime_owner") != "next":
            violations.append(Violation("cloud_campaign_page_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, f"current_runtime_owner={page_manifest.get('current_runtime_owner')}"))
        if page_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_page_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, f"legacy_fallback_allowed={page_manifest.get('legacy_fallback_allowed')}"))
        if page_manifest.get("delete_status") != "deletion_locked" or page_manifest.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_page_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, f"delete_status={page_manifest.get('delete_status')} replacement_status={page_manifest.get('replacement_status')}"))

    write_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_METHODS)
    if write_manifest is None:
        violations.append(Violation("cloud_campaign_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE))
    else:
        if write_manifest.get("current_runtime_owner") != "production_compat":
            violations.append(Violation("cloud_campaign_write_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"current_runtime_owner={write_manifest.get('current_runtime_owner')}"))
        if write_manifest.get("delete_status") == "deletion_locked" or write_manifest.get("replacement_status") == "locked":
            violations.append(Violation("cloud_campaign_write_manifest_mislocked", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"delete_status={write_manifest.get('delete_status')} replacement_status={write_manifest.get('replacement_status')}"))

    return violations


def check_wecom_tag_write_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/wecom_tag_write_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("wecom_tag_write_inventory_missing", str(inventory_path.relative_to(root)), "missing inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path, _methods in WECOM_TAG_WRITE_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_write_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for phrase in ("Frontend API Backend Contract Matrix", "SideEffectPlan", "production_compat rollback removed", "legacy_fallback_allowed=false", "deletion_locked", "real_external_call_executed=false"):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_write_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/customer_tags/api.py"
    admin_write_path = root / "aicrm_next/customer_tags/admin_write.py"
    commands_path = root / "aicrm_next/customer_tags/commands.py"
    write_repo_path = root / "aicrm_next/customer_tags/write_repo.py"
    main_path = root / "aicrm_next/main.py"
    production_compat_path = root / "aicrm_next/production_compat/api.py"

    if not api_path.exists():
        violations.append(Violation("wecom_tag_write_api_missing", str(api_path.relative_to(root)), "missing customer_tags api"))
    else:
        api_text = api_path.read_text(encoding="utf-8")
        if "write_router = APIRouter()" not in api_text:
            violations.append(Violation("wecom_tag_write_router_missing", str(api_path.relative_to(root)), "write_router = APIRouter()"))
        for route_path, _methods in WECOM_TAG_WRITE_ROUTES:
            if route_path not in api_text:
                violations.append(Violation("wecom_tag_write_exact_route_missing", str(api_path.relative_to(root)), route_path))
        if "execute_wecom_tag_write" not in api_text:
            violations.append(Violation("wecom_tag_write_command_executor_missing", str(api_path.relative_to(root)), "execute_wecom_tag_write"))

    for path, marker in [
        (admin_write_path, "execute_wecom_tag_write"),
        (commands_path, "WeComTagWriteCommand"),
        (write_repo_path, "WeComTagWriteRepository"),
    ]:
        if not path.exists():
            violations.append(Violation("wecom_tag_write_module_missing", str(path.relative_to(root)), marker))
            continue
        source = path.read_text(encoding="utf-8")
        if marker not in source:
            violations.append(Violation("wecom_tag_write_module_marker_missing", str(path.relative_to(root)), marker))
        for forbidden, code in {
            "forward_to_legacy_flask": "wecom_tag_write_legacy_forward",
            "legacy_flask_facade": "wecom_tag_write_legacy_facade",
            "X-AICRM-Compatibility-Facade": "wecom_tag_write_compatibility_facade",
            '"fallback_used": True': "wecom_tag_write_fallback_used_true",
            "'fallback_used': True": "wecom_tag_write_fallback_used_true",
            '"real_external_call_executed": True': "wecom_tag_write_real_external_call_true",
            "'real_external_call_executed': True": "wecom_tag_write_real_external_call_true",
            '"sync_executed": True': "wecom_tag_write_sync_executed_true",
            "'sync_executed': True": "wecom_tag_write_sync_executed_true",
            "requests.": "wecom_tag_write_direct_http_client",
            "httpx.": "wecom_tag_write_direct_http_client",
            "WeComTagLiveGateway": "wecom_tag_write_real_wecom_gateway",
            "mark_external_contact_tags": "wecom_tag_write_real_wecom_mutation",
        }.items():
            if forbidden in source:
                violations.append(Violation(code, str(path.relative_to(root)), forbidden))

    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        write_include = main_text.find("include_router(customer_tags_write_router)")
        compat_include = main_text.find("include_router(production_compat_router)")
        if write_include < 0:
            violations.append(Violation("wecom_tag_write_router_order", str(main_path.relative_to(root)), "customer_tags_write_router missing"))
        elif compat_include >= 0 and write_include > compat_include:
            violations.append(Violation("wecom_tag_write_router_order", str(main_path.relative_to(root)), "customer_tags_write_router must be included before production_compat_router"))

    if production_compat_path.exists():
        compat_sources = _decorated_route_function_sources(production_compat_path)
        for route_path in compat_sources:
            if route_path.startswith("/api/admin/wecom/tags") or route_path.startswith("/api/admin/wecom/tag-groups"):
                violations.append(
                    Violation(
                        "wecom_tag_write_production_compat_route",
                        str(production_compat_path.relative_to(root)),
                        route_path,
                        "WeCom tag read/write/sync production_compat rollback is deleted; keep live/fake routes in aicrm_next.customer_tags only.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_route = {(record.get("path_pattern"), tuple(record.get("methods") or [])): record for record in registry_records}
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_route = {(record.get("route_pattern"), tuple(record.get("methods") or [])): record for record in manifest_records}

    for route_path, methods in WECOM_TAG_WRITE_ROUTES:
        registry_record = registry_by_route.get((route_path, methods))
        if registry_record is None:
            violations.append(Violation("wecom_tag_write_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if registry_record.get("runtime_owner") != "next_command":
                violations.append(Violation("wecom_tag_write_registry_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_write_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
            if registry_record.get("legacy_source") not in {"", None}:
                violations.append(Violation("wecom_tag_write_registry_legacy_source", route_path, f"legacy_source={registry_record.get('legacy_source')}"))
            if registry_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_write_registry_adapter_mode", route_path, f"adapter_mode={registry_record.get('adapter_mode')}"))
            if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_write_registry_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))

        manifest_record = manifest_by_route.get((route_path, methods))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("wecom_tag_write_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_command":
                violations.append(Violation("wecom_tag_write_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_write_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("wecom_tag_write_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
            if manifest_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_write_manifest_adapter_mode", route_path, f"adapter_mode={manifest_record.get('adapter_mode')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_write_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def check_wecom_tag_live_mutation_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/wecom_tag_live_mutation_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("wecom_tag_live_mutation_inventory_missing", str(inventory_path.relative_to(root)), "missing inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path, _methods, _owner, _behavior in WECOM_TAG_LIVE_MUTATION_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_live_mutation_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for phrase in (
            "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
            "PlanWeComTagMarkCommand",
            "PlanWeComTagUnmarkCommand",
            "PlanCustomerTagAssignmentCommand",
            "PlanQuestionnaireTagSideEffectCommand",
            "real_external_call_executed=false",
            "wecom_api_called=false",
            "real_blocked",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_live_mutation_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/customer_tags/api.py"
    live_mutation_path = root / "aicrm_next/customer_tags/live_mutation.py"
    commands_path = root / "aicrm_next/customer_tags/mutation_commands.py"
    questionnaire_path = root / "aicrm_next/integration_gateway/questionnaire_adapters.py"
    compat_path = root / "aicrm_next/production_compat/api.py"

    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths & WECOM_TAG_LIVE_MUTATION_EXACT_ROUTES):
            violations.append(
                Violation(
                    "wecom_tag_live_mutation_production_compat_route",
                    str(compat_path.relative_to(root)),
                    route_path,
                    "WeCom live mutation routes are deletion_locked to Next and must not be reintroduced in production_compat.",
                )
            )

    for path, markers in [
        (api_path, ("mark_tags_live", "unmark_tags_live", "execute_wecom_tag_mutation", "live_gate_status")),
        (live_mutation_path, ("execute_wecom_tag_mutation", "InMemoryAuditLedger", "InMemorySideEffectPlanRepository", "wecom_api_called")),
        (commands_path, ("PlanWeComTagMarkCommand", "PlanWeComTagUnmarkCommand", "PlanCustomerTagAssignmentCommand", "PlanQuestionnaireTagSideEffectCommand")),
        (questionnaire_path, ("PlanQuestionnaireTagSideEffectCommand", "execute_wecom_tag_mutation")),
    ]:
        if not path.exists():
            violations.append(Violation("wecom_tag_live_mutation_module_missing", str(path.relative_to(root)), ",".join(markers)))
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in source:
                violations.append(Violation("wecom_tag_live_mutation_module_marker_missing", str(path.relative_to(root)), marker))

    for path in (api_path, live_mutation_path, commands_path):
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden, code in {
            "forward_to_legacy_flask": "wecom_tag_live_mutation_legacy_forward",
            "legacy_flask_facade": "wecom_tag_live_mutation_legacy_facade",
            "X-AICRM-Compatibility-Facade": "wecom_tag_live_mutation_compatibility_facade",
            '"fallback_used": True': "wecom_tag_live_mutation_fallback_used_true",
            "'fallback_used': True": "wecom_tag_live_mutation_fallback_used_true",
            '"real_external_call_executed": True': "wecom_tag_live_mutation_real_external_call_true",
            "'real_external_call_executed': True": "wecom_tag_live_mutation_real_external_call_true",
            '"wecom_api_called": True': "wecom_tag_live_mutation_wecom_api_called_true",
            "'wecom_api_called': True": "wecom_tag_live_mutation_wecom_api_called_true",
            "requests.": "wecom_tag_live_mutation_direct_http_client",
            "httpx.": "wecom_tag_live_mutation_direct_http_client",
            "WeComTagLiveGateway": "wecom_tag_live_mutation_real_wecom_gateway",
            "build_wecom_tag_live_gateway": "wecom_tag_live_mutation_real_wecom_gateway",
            "access_token": "wecom_tag_live_mutation_real_wecom_token",
            "externalcontact": "wecom_tag_live_mutation_real_wecom_api",
            "mark_external_contact_tags": "wecom_tag_live_mutation_real_wecom_mutation",
            "real_enabled=True": "wecom_tag_live_mutation_real_enabled_default",
            "real_enabled = True": "wecom_tag_live_mutation_real_enabled_default",
        }.items():
            if forbidden in source:
                violations.append(Violation(code, str(path.relative_to(root)), forbidden))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_route = {(record.get("path_pattern"), tuple(record.get("methods") or [])): record for record in registry_records}
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_route = {(record.get("route_pattern"), tuple(record.get("methods") or [])): record for record in manifest_records}

    for route_path, methods, owner, behavior in WECOM_TAG_LIVE_MUTATION_ROUTES:
        registry_record = registry_by_route.get((route_path, methods))
        if registry_record is None:
            violations.append(Violation("wecom_tag_live_mutation_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if registry_record.get("runtime_owner") != owner:
                violations.append(Violation("wecom_tag_live_mutation_registry_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_live_mutation_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
            if registry_record.get("runtime_owner") in {"production_compat", "legacy_forward"}:
                violations.append(Violation("wecom_tag_live_mutation_registry_legacy_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("external_side_effect_risk") != "high":
                violations.append(Violation("wecom_tag_live_mutation_registry_side_effect_risk", route_path, f"external_side_effect_risk={registry_record.get('external_side_effect_risk')}"))
            if registry_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_live_mutation_registry_adapter_mode", route_path, f"adapter_mode={registry_record.get('adapter_mode')}"))
            if registry_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
                violations.append(Violation("wecom_tag_live_mutation_registry_rollback_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')}"))
            if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_live_mutation_registry_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))

        manifest_record = manifest_by_route.get((route_path, methods))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_live_mutation_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("wecom_tag_live_mutation_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != behavior:
                violations.append(Violation("wecom_tag_live_mutation_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
                violations.append(Violation("wecom_tag_live_mutation_manifest_legacy_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_live_mutation_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_live_mutation_manifest_adapter_mode", route_path, f"adapter_mode={manifest_record.get('adapter_mode')}"))
            if manifest_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
                violations.append(Violation("wecom_tag_live_mutation_manifest_rollback_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_live_mutation_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def run_checks(*, strict: bool) -> dict:
    violations = (
        scan_source_tree(ROOT)
        + check_customer_read_model_legacy_deletion(ROOT)
        + check_production_compat_routes(ROOT)
        + check_messages_broad_wildcard_deletion(ROOT)
        + check_sidebar_readonly_closeout_lock(ROOT)
        + check_sidebar_jssdk_next_adapter(ROOT)
        + check_user_ops_next_native_preview(ROOT)
        + check_questionnaire_admin_read_next_native(ROOT)
        + check_questionnaire_admin_write_next_commandbus(ROOT)
        + check_questionnaire_h5_submit_next_commandbus(ROOT)
        + check_questionnaire_oauth_next_adapter(ROOT)
        + check_auth_wecom_wildcard_inventory(ROOT)
        + check_wecom_tag_read_next_native(ROOT)
        + check_wecom_tag_write_next_commandbus(ROOT)
        + check_wecom_tag_live_mutation_next_commandbus(ROOT)
        + check_media_library_closeout_lock(ROOT)
        + check_cloud_orchestrator_media_upload_closeout_lock(ROOT)
        + check_cloud_orchestrator_campaign_read_closeout_lock(ROOT)
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
