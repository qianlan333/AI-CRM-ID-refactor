from __future__ import annotations

from pathlib import Path

from scripts.check_no_new_legacy import (
    USER_OPS_PREVIEW_ROUTES,
    USER_OPS_READONLY_ROUTES,
    check_auth_wecom_wildcard_inventory,
    check_customer_read_model_legacy_deletion,
    check_messages_broad_wildcard_deletion,
    check_questionnaire_admin_read_next_native,
    check_questionnaire_admin_write_next_commandbus,
    check_questionnaire_h5_submit_next_commandbus,
    check_questionnaire_oauth_next_adapter,
    check_sidebar_readonly_closeout_lock,
    check_user_ops_next_native_preview,
    check_wecom_tag_live_mutation_next_commandbus,
    check_wecom_tag_read_next_native,
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
    h5_write.write_text("payload = {'fallback_used': False}\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/h5/questionnaires/{slug}/submit\n"
        "    runtime_owner: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: none\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    notes: Next CommandBus only; legacy rollback removed; configured questionnaire external push executes\n"
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
        "    adapter_mode: real_enabled\n"
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


def test_wecom_tag_live_mutation_guard_flags_legacy_route_and_real_gateway_drift(tmp_path: Path) -> None:
    inventory = tmp_path / "docs/architecture/wecom_tag_live_mutation_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/customer_tags/api.py"
    live_mutation = tmp_path / "aicrm_next/customer_tags/live_mutation.py"
    commands = tmp_path / "aicrm_next/customer_tags/mutation_commands.py"
    questionnaire = tmp_path / "aicrm_next/integration_gateway/questionnaire_adapters.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory.parent.mkdir(parents=True)
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    questionnaire.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    inventory.write_text(
        "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix\n"
        "/api/admin/wecom/tags/live/gate\n"
        "/api/admin/wecom/tags/live/mark\n"
        "/api/admin/wecom/tags/live/unmark\n"
        "PlanWeComTagMarkCommand PlanWeComTagUnmarkCommand PlanCustomerTagAssignmentCommand PlanQuestionnaireTagSideEffectCommand\n"
        "real_external_call_executed=false wecom_api_called=false real_blocked\n",
        encoding="utf-8",
    )
    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/admin/wecom/tags/live/mark', methods=['POST'])\n"
        "def legacy_live_mark():\n"
        "    pass\n",
        encoding="utf-8",
    )
    api.write_text(
        "def mark_tags_live():\n"
        "    return WeComTagLiveGateway()\n"
        "def unmark_tags_live():\n"
        "    return {'ok': True}\n"
        "def execute_wecom_tag_mutation():\n"
        "    return {'ok': True}\n"
        "def live_gate_status():\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    live_mutation.write_text(
        "class InMemoryAuditLedger: pass\n"
        "class InMemorySideEffectPlanRepository: pass\n"
        "def execute_wecom_tag_mutation():\n"
        "    return {'access_token': 'token', 'wecom_api_called': False}\n",
        encoding="utf-8",
    )
    commands.write_text(
        "class PlanWeComTagMarkCommand: pass\n"
        "class PlanWeComTagUnmarkCommand: pass\n"
        "class PlanCustomerTagAssignmentCommand: pass\n"
        "class PlanQuestionnaireTagSideEffectCommand: pass\n",
        encoding="utf-8",
    )
    questionnaire.write_text("PlanQuestionnaireTagSideEffectCommand = object\nexecute_wecom_tag_mutation = object\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/wecom/tags/live/gate\n"
        "    methods: [GET]\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/admin/wecom/tags/live/mark\n"
        "    methods: [POST, OPTIONS]\n"
        "    runtime_owner: next_command\n"
        "    legacy_fallback_allowed: true\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n"
        "  - path_pattern: /api/admin/wecom/tags/live/unmark\n"
        "    methods: [POST, OPTIONS]\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: false\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/wecom/tags/live/gate\n"
        "    methods: [GET]\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/admin/wecom/tags/live/mark\n"
        "    methods: [POST, OPTIONS]\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_primary_with_legacy_rollback\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n"
        "  - route_pattern: /api/admin/wecom/tags/live/unmark\n"
        "    methods: [POST, OPTIONS]\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )

    codes = {violation.code for violation in check_wecom_tag_live_mutation_next_commandbus(tmp_path)}

    assert "wecom_tag_live_mutation_production_compat_route" in codes
    assert "wecom_tag_live_mutation_real_wecom_gateway" in codes
    assert "wecom_tag_live_mutation_real_wecom_token" in codes
    assert "wecom_tag_live_mutation_registry_rollback_allowed" in codes
    assert "wecom_tag_live_mutation_registry_rollback_lifecycle" in codes
    assert "wecom_tag_live_mutation_manifest_behavior" in codes
    assert "wecom_tag_live_mutation_manifest_legacy_behavior" in codes
    assert "wecom_tag_live_mutation_manifest_rollback_allowed" in codes


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
    assert "questionnaire_oauth_registry_lifecycle" in codes
    assert "questionnaire_oauth_manifest_legacy_forward" in codes
    assert "questionnaire_oauth_manifest_lifecycle" in codes


def test_questionnaire_oauth_guard_allows_next_adapter_locked_with_retained_wildcard_rollback(tmp_path: Path) -> None:
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
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: ''\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/h5/wechat/oauth/callback\n"
        "    runtime_owner: next_adapter\n"
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: ''\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/h5/wechat/oauth/start\n"
        "    current_runtime_owner: next_adapter\n"
        "    production_behavior: next_oauth_adapter\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/h5/wechat/oauth/callback\n"
        "    current_runtime_owner: next_adapter\n"
        "    production_behavior: next_oauth_adapter\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )

    assert check_questionnaire_oauth_next_adapter(tmp_path) == []


def test_auth_wecom_guard_flags_exact_production_compat_and_missing_lifecycle(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    auth_api = tmp_path / "aicrm_next/auth_wecom/api.py"
    inventory = tmp_path / "docs/architecture/auth_wecom_route_inventory.md"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    auth_api.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/auth/wecom/start', methods=['GET'])\n"
        "@router.api_route('/auth/wecom/{path:path}', methods=['GET'])\n"
        "def auth_wecom_start():\n"
        "    pass\n",
        encoding="utf-8",
    )
    auth_api.write_text("payload = {'fallback_used': True, 'real_external_call_executed': True}\n", encoding="utf-8")
    inventory.write_text("/auth/wecom/start\n/auth/wecom/callback\n/auth/wecom/unknown\n/api/h5/wechat/oauth/unknown\n/api/h5/wechat/oauth/{path:path}\n/auth/wecom/{path:path}\n/api/h5/wechat/oauth/start\n/api/h5/wechat/oauth/callback\n", encoding="utf-8")
    registry.write_text("routes:\n", encoding="utf-8")
    manifest.write_text("routes:\n", encoding="utf-8")

    codes = {violation.code for violation in check_auth_wecom_wildcard_inventory(tmp_path)}

    assert "auth_wecom_production_compat_exact_route" in codes
    assert "auth_wecom_deleted_wildcard_reintroduced" in codes
    assert "auth_wecom_unregistered_wildcard" in codes
    assert "auth_wecom_fallback_used_true" in codes
    assert "auth_wecom_real_external_call_true" in codes
    assert "auth_wecom_registry_missing" in codes
    assert "auth_wecom_manifest_missing" in codes


def test_auth_wecom_guard_allows_locked_exact_routes_with_deleted_wildcards(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    auth_api = tmp_path / "aicrm_next/auth_wecom/api.py"
    inventory = tmp_path / "docs/architecture/auth_wecom_route_inventory.md"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    auth_api.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    compat.write_text("from fastapi import APIRouter\nwildcard_router = APIRouter()\n", encoding="utf-8")
    auth_api.write_text("payload = {'fallback_used': False, 'real_external_call_executed': False}\n", encoding="utf-8")
    inventory.write_text("/auth/wecom/start\n/auth/wecom/callback\n/auth/wecom/unknown\n/api/h5/wechat/oauth/unknown\n/api/h5/wechat/oauth/{path:path}\n/auth/wecom/{path:path}\n/api/h5/wechat/oauth/start\n/api/h5/wechat/oauth/callback\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /auth/wecom/start\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /auth/wecom/callback\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /auth/wecom/unknown\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/h5/wechat/oauth/unknown\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/h5/wechat/oauth*\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: legacy_deleted\n"
        "    replacement_status: deleted\n"
        "  - path_pattern: /auth/wecom*\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: legacy_deleted\n"
        "    replacement_status: deleted\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /auth/wecom/start\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /auth/wecom/callback\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /auth/wecom/unknown\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/h5/wechat/oauth/unknown\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/h5/wechat/oauth*\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: legacy_deleted\n"
        "    replacement_status: deleted\n"
        "  - route_pattern: /auth/wecom*\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: legacy_deleted\n"
        "    replacement_status: deleted\n",
        encoding="utf-8",
    )

    assert check_auth_wecom_wildcard_inventory(tmp_path) == []


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
        "    legacy_fallback_allowed: false\n"
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


def test_questionnaire_admin_write_guard_allows_next_commandbus_with_production_fallback(tmp_path: Path) -> None:
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
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: legacy_flask_facade\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: active_fallback\n"
        "    replacement_status: production_fallback\n"
        "    notes: Questionnaire admin write uses Next CommandBus locally and production_data_ready forwards through legacy_flask_facade\n"
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
        "    production_behavior: next_command_local_legacy_write_fallback\n"
        "    legacy_fallback_allowed: true\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: active_fallback\n"
        "    replacement_status: production_fallback\n"
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


def _write_wecom_tag_read_docs(
    tmp_path: Path,
    *,
    registry_owner: str = "next_native",
    registry_legacy_allowed: str = "false",
    registry_legacy_source: str = '""',
    registry_delete_status: str = "deletion_locked",
    registry_replacement_status: str = "locked",
    manifest_owner: str = "next",
    manifest_behavior: str = "next_exact",
    manifest_legacy_allowed: str = "false",
    manifest_delete_status: str = "deletion_locked",
    manifest_replacement_status: str = "locked",
    family_lifecycle: str = "active",
) -> None:
    inventory = tmp_path / "docs/architecture/wecom_tag_read_route_inventory.md"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text(
        "/api/admin/wecom/tags\n"
        "/api/admin/wecom/tags/{tag_id}\n"
        "/api/admin/wecom/tag-groups\n"
        "/api/admin/wecom/tag-groups/{group_id}\n"
        "/api/admin/wecom/tags*\n"
        "/api/admin/wecom/tag-groups*\n"
        "/api/sidebar/signup-tags/status\n"
        "Frontend API Backend Contract Matrix\n"
        "Write Out Of Scope\n"
        "External Side Effects Out Of Scope\n"
        "No separate sidebar tag catalog selector\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/admin/wecom/tags\n"
        f"    runtime_owner: {registry_owner}\n"
        f"    legacy_fallback_allowed: {registry_legacy_allowed}\n"
        f"    legacy_source: {registry_legacy_source}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_status: {registry_delete_status}\n"
        f"    replacement_status: {registry_replacement_status}\n"
        "  - path_pattern: /api/admin/wecom/tags/{tag_id}\n"
        f"    runtime_owner: {registry_owner}\n"
        f"    legacy_fallback_allowed: {registry_legacy_allowed}\n"
        f"    legacy_source: {registry_legacy_source}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_status: {registry_delete_status}\n"
        f"    replacement_status: {registry_replacement_status}\n"
        "  - path_pattern: /api/admin/wecom/tag-groups\n"
        f"    runtime_owner: {registry_owner}\n"
        f"    legacy_fallback_allowed: {registry_legacy_allowed}\n"
        f"    legacy_source: {registry_legacy_source}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_status: {registry_delete_status}\n"
        f"    replacement_status: {registry_replacement_status}\n"
        "  - path_pattern: /api/admin/wecom/tag-groups/{group_id}\n"
        f"    runtime_owner: {registry_owner}\n"
        f"    legacy_fallback_allowed: {registry_legacy_allowed}\n"
        f"    legacy_source: {registry_legacy_source}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_status: {registry_delete_status}\n"
        f"    replacement_status: {registry_replacement_status}\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/wecom/tags\n"
        f"    current_runtime_owner: {manifest_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {manifest_legacy_allowed}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {manifest_delete_status}\n"
        f"    replacement_status: {manifest_replacement_status}\n"
        "  - route_pattern: /api/admin/wecom/tags/{tag_id}\n"
        f"    current_runtime_owner: {manifest_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {manifest_legacy_allowed}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {manifest_delete_status}\n"
        f"    replacement_status: {manifest_replacement_status}\n"
        "  - route_pattern: /api/admin/wecom/tag-groups\n"
        f"    current_runtime_owner: {manifest_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {manifest_legacy_allowed}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {manifest_delete_status}\n"
        f"    replacement_status: {manifest_replacement_status}\n"
        "  - route_pattern: /api/admin/wecom/tag-groups/{group_id}\n"
        f"    current_runtime_owner: {manifest_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {manifest_legacy_allowed}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {manifest_delete_status}\n"
        f"    replacement_status: {manifest_replacement_status}\n"
        "  - route_pattern: /api/admin/wecom/tags*\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: guarded_preview\n"
        "    legacy_fallback_allowed: false\n"
        f"    delete_status: {family_lifecycle}\n"
        "    replacement_status: not_started\n"
        "  - route_pattern: /api/admin/wecom/tag-groups*\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: guarded_preview\n"
        "    legacy_fallback_allowed: false\n"
        f"    delete_status: {family_lifecycle}\n"
        "    replacement_status: not_started\n",
        encoding="utf-8",
    )


def test_wecom_tag_read_guard_flags_legacy_forward_and_lifecycle_drift(tmp_path: Path) -> None:
    api = tmp_path / "aicrm_next/customer_tags/api.py"
    read_model = tmp_path / "aicrm_next/customer_tags/read_model.py"
    main = tmp_path / "aicrm_next/main.py"
    api.parent.mkdir(parents=True)
    api.write_text(
        "from fastapi import APIRouter\n"
        "read_router = APIRouter()\n"
        "@read_router.get('/api/admin/wecom/tags')\n"
        "def list_admin_wecom_tags_read_model():\n"
        "    return forward_to_legacy_flask()\n"
        "@read_router.get('/api/admin/wecom/tags/{tag_id}')\n"
        "def get_admin_wecom_tag_read_model():\n"
        "    return {'sync_executed': True}\n"
        "@read_router.get('/api/admin/wecom/tag-groups')\n"
        "def list_admin_wecom_tag_groups_read_model():\n"
        "    return {'real_external_call_executed': True}\n"
        "@read_router.get('/api/admin/wecom/tag-groups/{group_id}')\n"
        "def get_admin_wecom_tag_group_read_model():\n"
        "    return {}\n"
        "def _read_catalog_payload():\n"
        "    return {'fallback_used': True}\n"
        "def _production_unavailable():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    read_model.write_text("httpx.post('https://example.invalid')\nsource = 'production_success_claimed'\n", encoding="utf-8")
    main.write_text(
        "app.include_router(production_compat_router)\n"
        "app.include_router(customer_tags_read_router)\n",
        encoding="utf-8",
    )
    _write_wecom_tag_read_docs(
        tmp_path,
        registry_owner="production_compat",
        registry_legacy_allowed="true",
        registry_legacy_source="production_compat",
        registry_delete_status="next_primary_with_legacy_rollback",
        registry_replacement_status="validating",
        manifest_owner="production_compat",
        manifest_behavior="legacy_forward",
        manifest_legacy_allowed="true",
        manifest_delete_status="next_primary_with_legacy_rollback",
        manifest_replacement_status="validating",
        family_lifecycle="deletion_locked",
    )
    production_compat = tmp_path / "aicrm_next/production_compat/api.py"
    production_compat.parent.mkdir(parents=True, exist_ok=True)
    production_compat.write_text(
        "_WRITE_FALLBACK_METHODS = ['GET', 'POST']\n"
        "@router.api_route('/api/admin/wecom/tags', methods=_ALL_METHODS)\n"
        "async def legacy_admin_wecom_tag_routes(): pass\n",
        encoding="utf-8",
    )

    codes = {violation.code for violation in check_wecom_tag_read_next_native(tmp_path)}

    assert "wecom_tag_read_legacy_forward" in codes
    assert "wecom_tag_read_fallback_used_true" in codes
    assert "wecom_tag_read_real_external_call_true" in codes
    assert "wecom_tag_read_sync_" + "executed_true" in codes
    assert "wecom_tag_read_direct_http_client" in codes
    assert "wecom_tag_read_production_success_claimed" in codes
    assert "wecom_tag_read_router_order" in codes
    assert "wecom_tag_read_production_compat_write_methods_include_read" in codes
    assert "wecom_tag_read_production_compat_read_route" in codes
    assert "wecom_tag_read_registry_owner" in codes
    assert "wecom_tag_read_registry_rollback_allowed" in codes
    assert "wecom_tag_read_registry_legacy_source" in codes
    assert "wecom_tag_read_registry_lifecycle" in codes
    assert "wecom_tag_read_manifest_owner" in codes
    assert "wecom_tag_read_manifest_behavior" in codes
    assert "wecom_tag_read_manifest_rollback_allowed" in codes
    assert "wecom_tag_read_manifest_lifecycle" in codes
    assert "wecom_tag_family_manifest_mislocked" in codes


def test_wecom_tag_read_guard_allows_next_read_primary_with_out_of_scope_families(tmp_path: Path) -> None:
    api = tmp_path / "aicrm_next/customer_tags/api.py"
    read_model = tmp_path / "aicrm_next/customer_tags/read_model.py"
    main = tmp_path / "aicrm_next/main.py"
    api.parent.mkdir(parents=True)
    api.write_text(
        "from fastapi import APIRouter\n"
        "read_router = APIRouter()\n"
        '@read_router.get("/api/admin/wecom/tags")\n'
        "def list_admin_wecom_tags_read_model():\n"
        "    return _read_catalog_payload()\n"
        '@read_router.get("/api/admin/wecom/tags/{tag_id}")\n'
        "def get_admin_wecom_tag_read_model():\n"
        "    return _read_catalog_payload()\n"
        '@read_router.get("/api/admin/wecom/tag-groups")\n'
        "def list_admin_wecom_tag_groups_read_model():\n"
        "    return _read_catalog_payload()\n"
        '@read_router.get("/api/admin/wecom/tag-groups/{group_id}")\n'
        "def get_admin_wecom_tag_group_read_model():\n"
        "    return _read_catalog_payload()\n"
        "def _read_catalog_payload():\n"
        "    return {'fallback_used': False, 'real_external_call_executed': False, 'sync_executed': False}\n"
        "def _production_unavailable():\n"
        "    return {'source_status': 'production_unavailable'}\n",
        encoding="utf-8",
    )
    read_model.write_text("class PostgresTagCatalogRepository: pass\n", encoding="utf-8")
    production_compat = tmp_path / "aicrm_next/production_compat/api.py"
    production_compat.parent.mkdir(parents=True, exist_ok=True)
    production_compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8")
    main.write_text(
        "app.include_router(customer_tags_read_router)\n"
        "app.include_router(production_compat_router)\n",
        encoding="utf-8",
    )
    _write_wecom_tag_read_docs(tmp_path)

    assert check_wecom_tag_read_next_native(tmp_path) == []
