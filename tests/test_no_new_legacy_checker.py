from __future__ import annotations

from pathlib import Path

from scripts.check_no_new_legacy import (
    USER_OPS_PREVIEW_ROUTES,
    USER_OPS_READONLY_ROUTES,
    check_customer_read_model_legacy_deletion,
    check_messages_broad_wildcard_deletion,
    check_questionnaire_admin_read_next_native,
    check_questionnaire_admin_write_next_commandbus,
    check_questionnaire_h5_submit_next_commandbus,
    check_questionnaire_oauth_next_adapter,
    check_sidebar_readonly_closeout_lock,
    check_user_ops_next_native_preview,
    scan_source_tree,
)


def test_no_new_legacy_checker_flags_disallowed_legacy_import(tmp_path: Path) -> None:
    target = tmp_path / "aicrm_next/new_api.py"
    target.parent.mkdir()
    target.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    violations = scan_source_tree(tmp_path)

    assert [violation.code for violation in violations] == ["legacy_flask_facade_import"]
    payload = violations[0].to_dict()
    assert payload["path"] == "aicrm_next/new_api.py"
    assert "route registry" in payload["remediation"]


def test_no_new_legacy_checker_exempts_tests_and_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs/note.py"
    tests = tmp_path / "tests/test_note.py"
    docs.parent.mkdir()
    tests.parent.mkdir()
    docs.write_text("from wecom_ability_service.db import get_db\n", encoding="utf-8")
    tests.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    assert scan_source_tree(tmp_path) == []


def test_questionnaire_h5_submit_guard_flags_legacy_route_and_lifecycle_drift(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/questionnaire/api.py"
    h5_write = tmp_path / "aicrm_next/questionnaire/h5_write.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/h5/questionnaires/{slug}/submit', methods=['POST'])\n"
        "def legacy_submit():\n"
        "    pass\n",
        encoding="utf-8",
    )
    api.write_text(
        "def public_submit_questionnaire():\n"
        "    return forward_to_legacy_flask()\n"
        "def public_questionnaire_client_diagnostics():\n"
        "    return {'fallback_used': True}\n",
        encoding="utf-8",
    )
    h5_write.write_text("payload = {'real_external_call_executed': True}\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/h5/questionnaires/{slug}/submit\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: production_compat\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: not_started\n"
        "    notes: legacy forward\n"
        "  - path_pattern: /api/h5/questionnaires/{slug}/client-diagnostics\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: production_compat\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: not_started\n"
        "    notes: legacy forward\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/h5/questionnaires/{slug}/submit\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_enabled\n"
        "    delete_ready: false\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: not_started\n"
        "  - route_pattern: /api/h5/questionnaires/{slug}/client-diagnostics\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_enabled\n"
        "    delete_ready: false\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: not_started\n",
        encoding="utf-8",
    )

    codes = {violation.code for violation in check_questionnaire_h5_submit_next_commandbus(tmp_path)}

    assert "questionnaire_h5_submit_production_compat_route" in codes
    assert "questionnaire_h5_submit_legacy_forward" in codes
    assert "questionnaire_h5_submit_fallback_used_true" in codes
    assert "questionnaire_h5_submit_real_external_call_true" in codes
    assert "questionnaire_h5_submit_registry_owner" in codes
    assert "questionnaire_h5_submit_registry_legacy_allowed" in codes
    assert "questionnaire_h5_submit_registry_legacy_source" in codes
    assert "questionnaire_h5_submit_registry_adapter_mode" in codes
    assert "questionnaire_h5_submit_registry_rollback_lifecycle" in codes
    assert "questionnaire_h5_submit_registry_delete_status" in codes
    assert "questionnaire_h5_submit_manifest_behavior" in codes
    assert "questionnaire_h5_submit_manifest_legacy_allowed" in codes
    assert "questionnaire_h5_submit_manifest_not_delete_ready" in codes
    assert "questionnaire_h5_submit_manifest_rollback_lifecycle" in codes
    assert "questionnaire_h5_submit_manifest_lifecycle" in codes


def test_questionnaire_h5_submit_guard_allows_next_commandbus_deletion_locked(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/questionnaire/api.py"
    h5_write = tmp_path / "aicrm_next/questionnaire/h5_write.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8")
    api.write_text(
        "def public_submit_questionnaire():\n"
        "    return execute_questionnaire_h5_submit()\n"
        "def public_questionnaire_client_diagnostics():\n"
        "    return execute_questionnaire_client_diagnostics()\n",
        encoding="utf-8",
    )
    h5_write.write_text("payload = {'fallback_used': False, 'real_external_call_executed': False}\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/h5/questionnaires/{slug}/submit\n"
        "    runtime_owner: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: none\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    notes: Next CommandBus only; legacy rollback removed; real_external_call_executed=false\n"
        "  - path_pattern: /api/h5/questionnaires/{slug}/client-diagnostics\n"
        "    runtime_owner: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: none\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    notes: Next CommandBus only; legacy rollback removed; real_external_call_executed=false\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/h5/questionnaires/{slug}/submit\n"
        "    current_runtime_owner: next_command\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_ready: true\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/h5/questionnaires/{slug}/client-diagnostics\n"
        "    current_runtime_owner: next_command\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_ready: true\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )

    assert check_questionnaire_h5_submit_next_commandbus(tmp_path) == []


def test_questionnaire_oauth_guard_flags_exact_legacy_route_and_lifecycle_drift(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/questionnaire/api.py"
    oauth = tmp_path / "aicrm_next/questionnaire/oauth.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/h5/wechat/oauth/start', methods=['GET'])\n"
        "def legacy_oauth_start():\n"
        "    pass\n",
        encoding="utf-8",
    )
    api.write_text(
        "def wechat_oauth_start():\n"
        "    return forward_to_legacy_flask()\n"
        "def wechat_oauth_callback():\n"
        "    return {'fallback_used': True}\n",
        encoding="utf-8",
    )
    oauth.write_text("payload = {'real_external_call_executed': False}\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/h5/wechat/oauth/start\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: fake\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n"
        "  - path_pattern: /api/h5/wechat/oauth/callback\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: fake\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/h5/wechat/oauth/start\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: fake\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n"
        "  - route_pattern: /api/h5/wechat/oauth/callback\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: fake\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n",
        encoding="utf-8",
    )

    codes = {violation.code for violation in check_questionnaire_oauth_next_adapter(tmp_path)}

    assert "questionnaire_oauth_production_compat_exact_route" in codes
    assert "questionnaire_oauth_legacy_forward" in codes
    assert "questionnaire_oauth_fallback_used_true" in codes
    assert "questionnaire_oauth_registry_owner" in codes
    assert "questionnaire_oauth_manifest_legacy_forward" in codes


def test_questionnaire_oauth_guard_allows_next_adapter_with_retained_wildcard_rollback(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/questionnaire/api.py"
    oauth = tmp_path / "aicrm_next/questionnaire/oauth.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/h5/wechat/oauth/{path:path}', methods=['GET'])\n"
        "def oauth_wildcard():\n"
        "    pass\n",
        encoding="utf-8",
    )
    api.write_text(
        "def wechat_oauth_start():\n"
        "    return StartWechatOAuthQuery()\n"
        "def wechat_oauth_callback():\n"
        "    return CompleteWechatOAuthCallbackCommand()\n",
        encoding="utf-8",
    )
    oauth.write_text("payload = {'fallback_used': False, 'real_external_call_executed': False}\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/h5/wechat/oauth/start\n"
        "    runtime_owner: next_adapter\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n"
        "  - path_pattern: /api/h5/wechat/oauth/callback\n"
        "    runtime_owner: next_adapter\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/h5/wechat/oauth/start\n"
        "    current_runtime_owner: next_adapter\n"
        "    production_behavior: next_oauth_adapter\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n"
        "  - route_pattern: /api/h5/wechat/oauth/callback\n"
        "    current_runtime_owner: next_adapter\n"
        "    production_behavior: next_oauth_adapter\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )

    assert check_questionnaire_oauth_next_adapter(tmp_path) == []


def test_customer_read_model_legacy_deletion_guard_flags_deleted_patterns(tmp_path: Path) -> None:
    crm = tmp_path / "aicrm_next/customer_read_model/application.py"
    script = tmp_path / "scripts/backfill_customer_read_model.py"
    crm.parent.mkdir(parents=True)
    script.parent.mkdir(parents=True)
    crm.write_text(
        "from aicrm_next.integration_gateway.legacy_customer_read_facade import get_customer_via_legacy\n"
        "CUSTOMER_READ_MODEL" + "_LEGACY_ROLLBACK_ENABLED = '1'\n"
        "LegacyShadowCustomerReadModelSource\n",
        encoding="utf-8",
    )
    script.write_text("target = get_settings().database_url\nsource = 'legacy-shadow'\n", encoding="utf-8")

    violations = check_customer_read_model_legacy_deletion(tmp_path)
    codes = {violation.code for violation in violations}

    assert "customer_read_legacy_facade_import" in codes
    assert "customer_read_legacy_rollback_flag" in codes
    assert "customer_read_legacy_shadow_source" in codes
    assert "customer_read_backfill_execute_uses_default_database" in codes
    assert "customer_read_backfill_legacy_source" in codes


def test_messages_broad_wildcard_deletion_guard_flags_legacy_forward_and_bad_lifecycle(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n"
        '@wildcard_router.api_route("/api/messages/{path:path}", methods=_ALL_METHODS)\n'
        "async def legacy_production_compat_routes(request):\n"
        "    return await forward_to_legacy_flask(request)\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/messages*\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_status: active\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/messages*\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_ready: false\n",
        encoding="utf-8",
    )

    violations = check_messages_broad_wildcard_deletion(tmp_path)
    codes = {violation.code for violation in violations}

    assert "messages_broad_wildcard_decorator" in codes
    assert "messages_broad_wildcard_legacy_forward" in codes
    assert "messages_broad_wildcard_registry_legacy_allowed" in codes
    assert "messages_broad_wildcard_registry_delete_status" in codes
    assert "messages_broad_wildcard_registry_replacement_status" in codes
    assert "messages_broad_wildcard_manifest_legacy_forward" in codes


def test_messages_broad_wildcard_deletion_guard_allows_exact_routes(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        '@router.get("/api/messages/{external_userid}")\n'
        '@router.get("/api/messages/{external_userid}/recent")\n'
        '@router.get("/api/messages/search")\n'
        "def exact_messages_routes():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/messages*\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: legacy_deleted\n"
        "    replacement_status: deleted\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/messages*\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n",
        encoding="utf-8",
    )

    assert check_messages_broad_wildcard_deletion(tmp_path) == []


def test_user_ops_next_native_preview_guard_flags_legacy_forward_and_real_external_calls(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    ops_api = tmp_path / "aicrm_next/ops_enrollment/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    ops_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text('@wildcard_router.api_route("/api/admin/user-ops/{path:path}", methods=_ALL_METHODS)\ndef user_ops_legacy():\n    return {}\n', encoding="utf-8")
    ops_api.write_text(
        "from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n"
        "payload = {'fallback_used': True, 'real_external_call_executed': True}\n"
        "mode = 'real_enabled'\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/user-ops*\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: true\n"
        "  - path_pattern: /api/admin/user-ops/broadcast/preview\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_enabled\n"
        "    replacement_status: not_started\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/user-ops*\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "  - route_pattern: /api/admin/user-ops/broadcast/preview\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n",
        encoding="utf-8",
    )

    violations = check_user_ops_next_native_preview(tmp_path)
    codes = {violation.code for violation in violations}

    assert "user_ops_production_compat_route" in codes
    assert "user_ops_legacy_forward" in codes
    assert "user_ops_fallback_used_true" in codes
    assert "user_ops_real_external_call_true" in codes
    assert "user_ops_real_enabled_marker" in codes
    assert "user_ops_registry_readonly_record_missing" in codes
    assert "user_ops_preview_registry_owner" in codes
    assert "user_ops_registry_legacy_rollback_reintroduced" in codes
    assert "user_ops_preview_registry_adapter_mode" in codes
    assert "user_ops_preview_registry_rollback_allowed" in codes
    assert "user_ops_manifest_legacy_rollback_reintroduced" in codes
    assert "user_ops_preview_manifest_behavior" in codes


def test_user_ops_next_native_preview_guard_allows_group_6_shape(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    ops_api = tmp_path / "aicrm_next/ops_enrollment/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    ops_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text("", encoding="utf-8")
    ops_api.write_text("payload = {'fallback_used': False, 'real_external_call_executed': False}\n", encoding="utf-8")
    readonly_registry = "".join(
        "  - path_pattern: " + route + "\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        for route in USER_OPS_READONLY_ROUTES
    )
    preview_registry = "".join(
        "  - path_pattern: " + route + "\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        for route in USER_OPS_PREVIEW_ROUTES
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/user-ops*\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "  - path_pattern: /admin/user-ops\n"
        "    runtime_owner: frontend_compat\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        + readonly_registry
        + preview_registry,
        encoding="utf-8",
    )
    readonly_manifest = "".join(
        "  - route_pattern: " + route + "\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_read_model_only\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        for route in USER_OPS_READONLY_ROUTES
    )
    preview_manifest = "".join(
        "  - route_pattern: " + route + "\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        for route in USER_OPS_PREVIEW_ROUTES
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/user-ops*\n"
        "    production_behavior: next_read_model_only\n"
        "    legacy_fallback_allowed: false\n"
        "  - route_pattern: /admin/user-ops\n"
        "    current_runtime_owner: frontend_compat\n"
        "    production_behavior: next_read_model_only\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        + readonly_manifest
        + preview_manifest,
        encoding="utf-8",
    )

    assert check_user_ops_next_native_preview(tmp_path) == []


def test_questionnaire_admin_read_guard_flags_legacy_rollback_and_compat(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    questionnaire_api = tmp_path / "aicrm_next/questionnaire/api.py"
    frontend_routes = tmp_path / "aicrm_next/frontend_compat/legacy_routes.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    questionnaire_api.parent.mkdir(parents=True)
    frontend_routes.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        '@router.get("/api/admin/questionnaires")\n'
        "def compat_questionnaires():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    questionnaire_api.write_text(
        "def list_questionnaires():\n"
        "    return {'fallback_used': True}\n",
        encoding="utf-8",
    )
    frontend_routes.write_text(
        "def admin_questionnaires():\n"
        "    return {'fallback_used': True}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/questionnaires\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: production_compat\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/questionnaires\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )

    violations = check_questionnaire_admin_read_next_native(tmp_path)
    codes = {violation.code for violation in violations}

    assert "questionnaire_admin_read_production_compat_route" in codes
    assert "questionnaire_admin_read_fallback_used_true" in codes
    assert "questionnaire_admin_read_page_fallback_used_true" in codes
    assert "questionnaire_admin_read_registry_owner" in codes
    assert "questionnaire_admin_read_registry_legacy_allowed" in codes
    assert "questionnaire_admin_read_registry_legacy_source" in codes
    assert "questionnaire_admin_read_registry_delete_status" in codes
    assert "questionnaire_admin_read_manifest_legacy_behavior" in codes
    assert "questionnaire_admin_read_manifest_legacy_allowed" in codes


def test_questionnaire_admin_read_guard_allows_locked_read_and_out_of_scope_routes(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    questionnaire_api = tmp_path / "aicrm_next/questionnaire/api.py"
    frontend_routes = tmp_path / "aicrm_next/frontend_compat/legacy_routes.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    questionnaire_api.parent.mkdir(parents=True)
    frontend_routes.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    read_routes = [
        ("/admin/questionnaires", "frontend_compat", "frontend_compat"),
        ("/admin/questionnaires/new", "frontend_compat", "frontend_compat"),
        ("/admin/questionnaires/{questionnaire_id}", "frontend_compat", "frontend_compat"),
        ("/api/admin/questionnaires", "next_native", "next"),
        ("/api/admin/questionnaires/{questionnaire_id}", "next_native", "next"),
        ("/api/admin/questionnaires/{questionnaire_id}/questions", "next_native", "next"),
        ("/api/admin/questionnaires/{questionnaire_id}/results", "next_native", "next"),
        ("/api/admin/questionnaires/{questionnaire_id}/submissions", "next_native", "next"),
    ]

    compat.write_text(
        '@router.api_route("/api/h5/wechat/oauth/{path:path}", methods=["GET"])\n'
        "def oauth_out_of_scope():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    questionnaire_api.write_text(
        "def list_questionnaires():\n"
        "    return {'fallback_used': False}\n"
        "def get_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def get_questionnaire_questions():\n"
        "    return {'fallback_used': False}\n"
        "def get_questionnaire_results():\n"
        "    return {'fallback_used': False}\n"
        "def get_questionnaire_submissions():\n"
        "    return {'fallback_used': False}\n",
        encoding="utf-8",
    )
    frontend_routes.write_text(
        "def admin_questionnaires():\n"
        "    return {'fallback_used': False}\n"
        "def admin_questionnaire_new():\n"
        "    return {'fallback_used': False}\n"
        "def admin_questionnaire_detail():\n"
        "    return {'fallback_used': False}\n"
        "def _questionnaire_editor_response():\n"
        "    return {'fallback_used': False}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        + "".join(
            f"  - path_pattern: {route}\n"
            f"    runtime_owner: {registry_owner}\n"
            "    legacy_fallback_allowed: false\n"
            "    legacy_source: ''\n"
            "    delete_status: deletion_locked\n"
            "    replacement_status: locked\n"
            for route, registry_owner, _manifest_owner in read_routes
        )
        + "  - path_pattern: /api/admin/questionnaires*\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n"
        "    legacy_fallback_allowed: true\n"
        "  - path_pattern: /api/h5/questionnaires*\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n"
        "    legacy_fallback_allowed: true\n"
        "  - path_pattern: /api/h5/wechat/oauth*\n"
        "    delete_status: active\n"
        "    replacement_status: not_started\n"
        "    legacy_fallback_allowed: true\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        + "".join(
            f"  - route_pattern: {route}\n"
            f"    current_runtime_owner: {manifest_owner}\n"
            "    production_behavior: next_read_model_only\n"
            "    legacy_fallback_allowed: false\n"
            "    delete_status: deletion_locked\n"
            "    replacement_status: locked\n"
            for route, _registry_owner, manifest_owner in read_routes
        ),
        encoding="utf-8",
    )

    assert check_questionnaire_admin_read_next_native(tmp_path) == []


def test_questionnaire_admin_write_guard_flags_legacy_and_lifecycle_drift(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    questionnaire_api = tmp_path / "aicrm_next/questionnaire/api.py"
    admin_write = tmp_path / "aicrm_next/questionnaire/admin_write.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    questionnaire_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        '@router.api_route("/api/admin/questionnaires/{questionnaire_id}/publish", methods=["POST"])\n'
        "def legacy_publish():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    questionnaire_api.write_text(
        "def create_questionnaire():\n"
        "    return {'fallback_used': True}\n",
        encoding="utf-8",
    )
    admin_write.write_text(
        "def execute():\n"
        "    return {'real_external_call_executed': True}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/questionnaires*\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: production_compat\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n"
        "    notes: wrong\n"
        "  - path_pattern: /api/admin/questionnaires/{questionnaire_id}/export\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    adapter_mode: none\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/questionnaires*\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n"
        "  - route_pattern: /api/admin/questionnaires/{questionnaire_id}/export\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )

    violations = check_questionnaire_admin_write_next_commandbus(tmp_path)
    codes = {violation.code for violation in violations}

    assert "questionnaire_admin_write_production_compat_route" in codes
    assert "questionnaire_admin_write_fallback_used_true" in codes
    assert "questionnaire_admin_write_real_external_call_true" in codes
    assert "questionnaire_admin_write_registry_owner" in codes
    assert "questionnaire_admin_write_registry_legacy_allowed" in codes
    assert "questionnaire_admin_write_registry_legacy_source" in codes
    assert "questionnaire_admin_write_registry_adapter_mode" in codes
    assert "questionnaire_admin_write_registry_delete_status" in codes
    assert "questionnaire_admin_write_manifest_behavior" in codes
    assert "questionnaire_admin_write_manifest_legacy_allowed" in codes


def test_questionnaire_admin_write_guard_allows_locked_next_commandbus_closeout(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    questionnaire_api = tmp_path / "aicrm_next/questionnaire/api.py"
    admin_write = tmp_path / "aicrm_next/questionnaire/admin_write.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    questionnaire_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text("", encoding="utf-8")
    questionnaire_api.write_text(
        "def create_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def update_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def duplicate_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def publish_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def disable_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def enable_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def delete_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def export_questionnaire():\n"
        "    return {'fallback_used': False}\n"
        "def export_questionnaire_preview():\n"
        "    return {'fallback_used': False}\n",
        encoding="utf-8",
    )
    admin_write.write_text(
        "def execute():\n"
        "    return {'fallback_used': False, 'real_external_call_executed': False}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/questionnaires*\n"
        "    runtime_owner: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: ''\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    notes: Questionnaire admin write legacy rollback removed; Next CommandBus only\n"
        "  - path_pattern: /api/admin/questionnaires/{questionnaire_id}/export\n"
        "    runtime_owner: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/questionnaires*\n"
        "    current_runtime_owner: next_command\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/admin/questionnaires/{questionnaire_id}/export\n"
        "    current_runtime_owner: next_command\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )

    assert check_questionnaire_admin_write_next_commandbus(tmp_path) == []


def test_sidebar_readonly_closeout_guard_flags_legacy_fallback_and_bad_lifecycle(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    customer_api = tmp_path / "aicrm_next/customer_read_model/api.py"
    identity_api = tmp_path / "aicrm_next/identity_contact/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    customer_api.parent.mkdir(parents=True)
    identity_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        '@router.api_route("/api/sidebar/profile", methods=["GET"])\n'
        '@router.api_route("/api/sidebar/bind-mobile", methods=["POST"])\n'
        "def legacy_profile():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    customer_api.write_text(
        '@router.get("/api/sidebar/profile")\n'
        "def sidebar_profile():\n"
        "    from aicrm_next.integration_gateway import legacy_sidebar_read_facade\n"
        "    return {\"fallback_used\": True}\n",
        encoding="utf-8",
    )
    identity_api.write_text("", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/sidebar/profile\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_status: active\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/sidebar/profile\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "  - route_pattern: /api/sidebar/bind-mobile\n"
        "    production_behavior: readonly_facade\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n",
        encoding="utf-8",
    )

    violations = check_sidebar_readonly_closeout_lock(tmp_path)
    codes = {violation.code for violation in violations}

    assert "sidebar_readonly_production_compat_route" in codes
    assert "sidebar_readonly_legacy_facade" in codes
    assert "sidebar_readonly_fallback_used_true" in codes
    assert "sidebar_readonly_registry_legacy_allowed" in codes
    assert "sidebar_readonly_registry_delete_status" in codes
    assert "sidebar_readonly_manifest_legacy_forward" in codes
    assert "sidebar_write_production_compat_route" in codes
    assert "sidebar_write_manifest_behavior" in codes


def test_sidebar_readonly_closeout_guard_allows_locked_readonly_and_out_of_scope_write_routes(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    customer_api = tmp_path / "aicrm_next/customer_read_model/api.py"
    identity_api = tmp_path / "aicrm_next/identity_contact/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    customer_api.parent.mkdir(parents=True)
    identity_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text('@router.api_route("/api/sidebar/jssdk-config", methods=["GET"])\ndef jssdk_route():\n    return {}\n', encoding="utf-8")
    customer_api.write_text(
        '@router.get("/api/sidebar/profile")\n'
        "def sidebar_profile():\n"
        "    return {\"route_owner\": \"ai_crm_next\", \"fallback_used\": False}\n",
        encoding="utf-8",
    )
    identity_api.write_text(
        '@router.get("/api/sidebar/binding-status")\n'
        "def sidebar_binding_status():\n"
        "    return {\"route_owner\": \"ai_crm_next\", \"fallback_used\": False}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/sidebar/profile\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/sidebar/binding-status\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/sidebar/bind-mobile\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/signup-tags/mark\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/lead-pool/upsert-class-term\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/marketing-status/set-followup-segment\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/marketing-status/mark-enrolled\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/marketing-status/unmark-enrolled\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/v2/profile\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/v2/materials/send\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/sidebar/profile\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: readonly_facade\n"
        "    legacy_fallback_allowed: false\n"
        "  - route_pattern: /api/sidebar/binding-status\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: readonly_facade\n"
        "    legacy_fallback_allowed: false\n"
        "  - route_pattern: /api/sidebar/bind-mobile\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/signup-tags/mark\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/lead-pool/upsert-class-term\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/marketing-status/set-followup-segment\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/marketing-status/mark-enrolled\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/marketing-status/unmark-enrolled\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/v2/profile\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/v2/materials/send\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/jssdk-config\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_ready: false\n",
        encoding="utf-8",
    )

    violations = check_sidebar_readonly_closeout_lock(tmp_path)
    codes = {violation.code for violation in violations}

    assert "sidebar_readonly_production_compat_route" not in codes
    assert "sidebar_readonly_legacy_facade" not in codes
    assert "sidebar_write_production_compat_route" not in codes
    assert "sidebar_write_manifest_legacy_allowed" not in codes
