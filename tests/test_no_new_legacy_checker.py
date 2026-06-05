from __future__ import annotations

from pathlib import Path

from scripts.check_no_new_legacy import (
    USER_OPS_PREVIEW_ROUTES,
    USER_OPS_READONLY_ROUTES,
    check_admin_auth_login_closeout_lock,
    check_auth_wecom_wildcard_inventory,
    check_automation_conversion_timers_next_safe_mode,
    check_automation_member_actions_next_safe_mode,
    check_automation_overview_pools_next_read_model,
    check_automation_workspace_runtime_next_safe_mode,
    check_cloud_orchestrator_media_upload_closeout_lock,
    check_cloud_orchestrator_campaign_read_closeout_lock,
    check_cloud_orchestrator_campaign_write_next_commandbus,
    check_customer_read_model_legacy_deletion,
    check_media_library_closeout_lock,
    check_messages_broad_wildcard_deletion,
    check_payment_wildcard_final_closeout_lock,
    check_post_legacy_architecture_freeze,
    check_public_product_pay_closeout_lock,
    check_questionnaire_admin_read_next_native,
    check_questionnaire_admin_write_next_commandbus,
    check_questionnaire_h5_submit_next_commandbus,
    check_questionnaire_oauth_next_adapter,
    check_sidebar_readonly_closeout_lock,
    check_sidebar_jssdk_next_adapter,
    check_user_ops_next_native_preview,
    check_wecom_tag_live_mutation_next_commandbus,
    check_final_legacy_exit_cleanup,
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


def test_admin_auth_login_guard_flags_production_compat_and_direct_exchange(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    auth_api = tmp_path / "aicrm_next/admin_auth/api.py"
    inventory = tmp_path / "docs/architecture/admin_auth_login_route_inventory.md"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    auth_api.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/login', methods=['GET'])\n"
        "@router.api_route('/logout', methods=['GET'])\n"
        "def legacy_auth(): pass\n",
        encoding="utf-8",
    )
    auth_api.write_text(
        '"fallback_used": True\n'
        "exchange_code_for_wecom_user()\n",
        encoding="utf-8",
    )
    inventory.write_text("incomplete\n", encoding="utf-8")
    registry.write_text("routes: []\n", encoding="utf-8")
    manifest.write_text("routes: []\n", encoding="utf-8")

    codes = {violation.code for violation in check_admin_auth_login_closeout_lock(tmp_path)}

    assert "admin_auth_login_production_compat_route" in codes
    assert "admin_auth_direct_wecom_exchange" in codes
    assert "admin_auth_fallback_true" in codes
    assert "admin_auth_login_registry_missing" in codes
    assert "admin_auth_login_manifest_missing" in codes


def test_payment_wildcard_final_guard_flags_final_fallback_and_real_markers(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    commerce_api = tmp_path / "aicrm_next/commerce/api.py"
    commerce_app = tmp_path / "aicrm_next/commerce/application.py"
    inventory = tmp_path / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    commerce_api.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/admin/wechat-pay/{path:path}', methods=['GET'])\n"
        "def legacy_payment(): return forward_to_legacy_flask()\n",
        encoding="utf-8",
    )
    commerce_api.write_text(
        '"fallback_used": True\n'
        '"real_external_call_executed": True\n'
        '"payment_request_executed": True\n'
        '"provider_signature_verified": True\n'
        '"real_refund_executed": True\n',
        encoding="utf-8",
    )
    commerce_app.write_text("requests.post('https://pay.example.invalid')\n", encoding="utf-8")
    inventory.write_text("incomplete\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - route_id: admin_wechat_pay_wildcard_final_closeout\n"
        "    path_pattern: /api/admin/wechat-pay/{path:path}\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: production_compat\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/wechat-pay*\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_ready: false\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )

    codes = {violation.code for violation in check_payment_wildcard_final_closeout_lock(tmp_path)}

    assert "payment_wildcard_final_inventory_boundary_missing" in codes
    assert "payment_wildcard_final_production_compat_facade" in codes
    assert "payment_wildcard_final_production_compat_route" in codes
    assert "payment_wildcard_final_fallback_true" in codes
    assert "payment_wildcard_final_real_external_call_true" in codes
    assert "payment_wildcard_final_payment_request_true" in codes
    assert "payment_wildcard_final_signature_verified_true" in codes
    assert "payment_wildcard_final_real_refund_true" in codes
    assert "payment_wildcard_final_direct_http_client" in codes
    assert "payment_wildcard_final_registry_owner" in codes
    assert "payment_wildcard_final_registry_legacy_allowed" in codes
    assert "payment_wildcard_final_manifest_owner" in codes
    assert "payment_wildcard_final_manifest_legacy_forward" in codes


def test_public_product_guard_flags_public_fallback_and_payment_execution(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    public_api = tmp_path / "aicrm_next/public_product/api.py"
    inventory = tmp_path / "docs/architecture/public_product_pay_route_inventory.md"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    public_api.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "wildcard_router = APIRouter()\n"
        '@router.api_route("/p/{path:path}", methods=["GET"])\n'
        '@wildcard_router.api_route("/api/products/{path:path}", methods=["GET"])\n'
        "def legacy_public(): pass\n",
        encoding="utf-8",
    )
    public_api.write_text(
        '"payment_request_executed": True\n'
        "create_wap_order()\n",
        encoding="utf-8",
    )
    inventory.write_text("incomplete\n", encoding="utf-8")
    registry.write_text("routes: []\n", encoding="utf-8")
    manifest.write_text("routes: []\n", encoding="utf-8")

    codes = {violation.code for violation in check_public_product_pay_closeout_lock(tmp_path)}

    assert "public_product_production_compat_route" in codes
    assert "public_product_wildcard_production_compat_route" in codes
    assert "public_product_payment_request" in codes
    assert "public_product_payment_request_true" in codes
    assert "public_product_registry_missing" in codes
    assert "public_product_manifest_missing" in codes


def test_public_product_guard_allows_next_h5_wechat_pay_markers(tmp_path: Path) -> None:
    h5_pay = tmp_path / "aicrm_next/public_product/h5_wechat_pay.py"
    h5_pay.parent.mkdir(parents=True)
    h5_pay.write_text(
        "from wecom_ability_service.infra.wechat_oauth import exchange_wechat_oauth_code\n"
        "from aicrm_next.commerce.wechat_pay_client import WeChatPayClient\n"
        "def create_jsapi_order_response():\n"
        "    access_token = ''\n"
        "    return WeChatPayClient, access_token\n",
        encoding="utf-8",
    )

    source_codes = {violation.code for violation in scan_source_tree(tmp_path)}
    closeout_codes = {violation.code for violation in check_public_product_pay_closeout_lock(tmp_path)}

    assert "wecom_ability_service_import" not in source_codes
    assert "public_product_direct_wechat_pay" not in closeout_codes
    assert "public_product_access_token_marker" not in closeout_codes
    assert "public_product_payment_request" not in closeout_codes


def test_no_new_legacy_checker_exempts_tests_and_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs/note.py"
    tests = tmp_path / "tests/test_note.py"
    docs.parent.mkdir()
    tests.parent.mkdir()
    docs.write_text("from wecom_ability_service.db import get_db\n", encoding="utf-8")
    tests.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    assert scan_source_tree(tmp_path) == []


def test_post_legacy_architecture_freeze_guard_flags_deleted_handler_registration(tmp_path: Path) -> None:
    docs = tmp_path / "docs/architecture"
    dev_docs = tmp_path / "docs/development"
    http = tmp_path / "wecom_ability_service/http"
    next_root = tmp_path / "aicrm_next"
    docs.mkdir(parents=True)
    dev_docs.mkdir(parents=True)
    http.mkdir(parents=True)
    next_root.mkdir(parents=True)

    (docs / "post_legacy_next_development_rules.md").write_text(
        "所有新功能必须 Next-owned\n"
        "禁止新增 production_compat\n"
        "禁止新增 legacy Flask forward\n"
        "禁止新增 compatibility facade\n"
        "route registry\n"
        "production route ownership manifest\n"
        "aicrm_next.customer_read_model\n"
        "aicrm_next.cloud_orchestrator\n"
        "aicrm_next.commerce\n"
        "aicrm_next.media_library\n"
        "aicrm_next.customer_tags\n"
        "aicrm_next.questionnaire\n"
        "duplicate checkout\nduplicate media upload\nduplicate customer selector\n"
        "duplicate tag catalog\nduplicate broadcast sender\nWeComClient.from_app\n"
        "real_external_call_executed=True\nreal_enabled default\n",
        encoding="utf-8",
    )
    (dev_docs / "codex_post_legacy_development_contract.md").write_text(
        "每次开发前必须读取\n"
        "existing module search\n"
        "不允许恢复 `production_compat`\n"
        "不允许新增 `forward_to_legacy_flask`\n"
        "不允许新建 legacy facade\n"
        "不允许默认真实外部调用\n"
        "不允许不登记 route owner\n"
        "不允许跳过 strict guard\n",
        encoding="utf-8",
    )
    (docs / "post_legacy_legacy_module_prune_inventory.md").write_text(
        "legacy module / package | 替代 Next 模块 | 删除决策\n"
        "`wecom_ability_service/http/admin_hxc_dashboard.py` | next | `deleted`\n"
        "`wecom_ability_service/http/admin_auth_routes.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_campaigns.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_campaign_details.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_media.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_endpoint.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_pages.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_plans.py` | next | `deleted`\n"
        "`wecom_ability_service/http/cloud_orchestrator_segments.py` | next | `deleted`\n"
        "`wecom_ability_service/http/automation_conversion.py` | next | keep_temporarily_historical\n"
        "`wecom_ability_service/http/automation_conversion_runtime_api.py` | next | keep_temporarily_historical\n"
        "`wecom_ability_service/http/automation_conversion_task_runtime.py` | next | keep_temporarily_historical\n"
        "`wecom_ability_service/http/automation_conversion_execution_outbound.py` | next | keep_temporarily_historical\n"
        "`wecom_ability_service/http/automation_conversion_member_api.py` | next | keep_temporarily_historical\n"
        "`wecom_ability_service/http/customer_automation.py` | next | keep_temporarily_historical\n",
        encoding="utf-8",
    )
    (http / "__init__.py").write_text("from .admin_auth_routes import register_routes\n", encoding="utf-8")
    (http / "admin_auth_routes.py").write_text("def register_routes(bp): pass\n", encoding="utf-8")
    (next_root / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")

    codes = {violation.code for violation in check_post_legacy_architecture_freeze(tmp_path)}

    assert "post_legacy_deleted_handler_still_exists" in codes
    assert "post_legacy_deleted_handler_still_registered" in codes


def test_final_cleanup_guard_flags_reintroduced_production_compat_source(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    main = tmp_path / "aicrm_next/main.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    main.parent.mkdir(parents=True, exist_ok=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\nwildcard_router = APIRouter()\n", encoding="utf-8")
    main.write_text("from fastapi import FastAPI\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - route_id: public_h5_regression\n"
        "    path_pattern: /api/h5/questionnaires*\n"
        "    methods: [GET]\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    legacy_source: production_compat\n"
        "    delete_status: active\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text("routes: []\n", encoding="utf-8")

    codes = {violation.code for violation in check_final_legacy_exit_cleanup(tmp_path)}

    assert "final_cleanup_registry_legacy_source" in codes
    assert "final_cleanup_registry_unlocked_legacy_source" in codes


def _write_cloud_media_upload_docs(
    tmp_path: Path,
    *,
    locked: bool = True,
    include_production_compat_route: bool = False,
) -> None:
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory = tmp_path / "docs/architecture/cloud_orchestrator_media_upload_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    cloud_api = tmp_path / "aicrm_next/cloud_orchestrator/api.py"
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    compat.parent.mkdir(parents=True, exist_ok=True)
    cloud_api.parent.mkdir(parents=True, exist_ok=True)

    legacy_allowed = "false" if locked else "true"
    legacy_source = '""' if locked else "production_compat"
    registry_delete_status = "deletion_locked" if locked else "next_primary_with_legacy_rollback"
    replacement_status = "locked" if locked else "validating"
    delete_ready = "true" if locked else "false"

    registry.write_text(
        "routes:\n"
        "  - route_id: cloud_orchestrator_media_upload_adapter\n"
        "    path_pattern: /api/admin/cloud-orchestrator/media/upload\n"
        "    methods: [POST, OPTIONS]\n"
        "    runtime_owner: next_adapter\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: production\n"
        f"    delete_status: {registry_delete_status}\n"
        f"    replacement_status: {replacement_status}\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/cloud-orchestrator/media/upload\n"
        "    methods: [POST, OPTIONS]\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_adapter_real_upload\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        "    adapter_mode: production\n"
        f"    delete_status: {registry_delete_status}\n"
        f"    replacement_status: {replacement_status}\n",
        encoding="utf-8",
    )
    inventory.write_text(
        "Frontend ↔ API ↔ Backend Contract Matrix\n"
        "Deletion Closeout Status Matrix\n"
        "production_compat rollback removed\n"
        "Next adapter only\n"
        "legacy_fallback_allowed=false\n"
        "deletion_locked\n"
        "real_external_call_executed=true\n"
        "wecom_media_upload_executed=true\n",
        encoding="utf-8",
    )
    if include_production_compat_route:
        compat.write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            '@router.api_route("/api/admin/cloud-orchestrator/media/upload", methods=["POST", "OPTIONS"])\n'
            "async def legacy_route(request):\n"
            "    return None\n",
            encoding="utf-8",
        )
    else:
        compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8")
    cloud_api.write_text("def route():\n    return {'real_external_call_executed': False}\n", encoding="utf-8")


def test_cloud_orchestrator_media_upload_closeout_guard_passes_current_repo() -> None:
    assert check_cloud_orchestrator_media_upload_closeout_lock() == []


def test_cloud_orchestrator_media_upload_closeout_guard_blocks_rollback(tmp_path: Path) -> None:
    _write_cloud_media_upload_docs(tmp_path, locked=False, include_production_compat_route=True)

    violations = check_cloud_orchestrator_media_upload_closeout_lock(tmp_path)
    codes = {violation.code for violation in violations}

    assert "cloud_media_upload_production_compat_route" in codes
    assert "cloud_media_upload_registry_legacy_allowed" in codes
    assert "cloud_media_upload_registry_rollback_lifecycle" in codes
    assert "cloud_media_upload_manifest_legacy_allowed" in codes
    assert "cloud_media_upload_manifest_rollback_lifecycle" in codes


def _write_cloud_campaign_read_docs(tmp_path: Path, *, locked: bool = True, compat_get: bool = False) -> None:
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory = tmp_path / "docs/architecture/cloud_orchestrator_campaigns_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/cloud_orchestrator/api.py"
    read_model = tmp_path / "aicrm_next/cloud_orchestrator/campaigns_read.py"
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    compat.parent.mkdir(parents=True, exist_ok=True)
    api.parent.mkdir(parents=True, exist_ok=True)

    legacy_allowed = "false" if locked else "true"
    legacy_source = '""' if locked else "production_compat"
    delete_status = "deletion_locked" if locked else "next_primary_with_legacy_rollback"
    replacement_status = "locked" if locked else "validating"
    delete_ready = "true" if locked else "false"
    write_owner = "next_command" if locked else "production_compat"
    write_legacy_allowed = "false" if locked else "true"
    write_legacy_source = '""' if locked else "production_compat"
    write_delete_ready = "true" if locked else "false"
    write_delete_status = "deletion_locked" if locked else "active"
    write_replacement_status = "locked" if locked else "not_started"
    write_behavior = "next_command" if locked else "legacy_forward"

    registry.write_text(
        "routes:\n"
        "  - route_id: cloud_orchestrator_campaigns_read_family\n"
        "    path_pattern: /api/admin/cloud-orchestrator/campaigns*\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {'next_read_model' if locked else 'production_compat'}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: cloud_orchestrator_campaigns_page\n"
        "    path_pattern: /admin/cloud-orchestrator/campaigns\n"
        "    methods: [GET]\n"
        "    runtime_owner: frontend_compat over Next read APIs\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    legacy_source: \"\"\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: cloud_orchestrator_campaigns_write_legacy_family\n"
        "    path_pattern: /api/admin/cloud-orchestrator/campaigns*\n"
        "    methods: [POST, PUT, PATCH, DELETE, OPTIONS]\n"
        f"    runtime_owner: {write_owner}\n"
        f"    legacy_fallback_allowed: {write_legacy_allowed}\n"
        f"    legacy_source: {write_legacy_source}\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        f"    delete_status: {write_delete_status}\n"
        f"    replacement_status: {write_replacement_status}\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/cloud-orchestrator/campaigns*\n"
        "    methods: [GET]\n"
        "    current_runtime_owner: next\n"
        f"    production_behavior: {'next_exact' if locked else 'legacy_forward'}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_pattern: /admin/cloud-orchestrator/campaigns\n"
        "    methods: [GET]\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    external_side_effect_risk: none\n"
        "    adapter_mode: none\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_pattern: /api/admin/cloud-orchestrator/campaigns*\n"
        "    methods: [POST, PUT, PATCH, DELETE, OPTIONS]\n"
        f"    current_runtime_owner: {write_owner}\n"
        f"    production_behavior: {write_behavior}\n"
        f"    legacy_fallback_allowed: {write_legacy_allowed}\n"
        "    external_side_effect_risk: real_blocked\n"
        "    adapter_mode: real_blocked\n"
        f"    delete_ready: {write_delete_ready}\n"
        f"    delete_status: {write_delete_status}\n"
        f"    replacement_status: {write_replacement_status}\n",
        encoding="utf-8",
    )
    inventory.write_text(
        "Frontend API Backend Contract Matrix\n"
        "Deletion Closeout Status Matrix\n"
        "legacy_fallback_allowed=false\n"
        "deletion_locked\n"
        "legacy fallback removed\n"
        "write controls locked on Next CommandBus\n"
        "No real WeCom send\n"
        "No automation runtime\n"
        "/api/admin/cloud-orchestrator/campaigns\n"
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}\n"
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members\n"
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps\n",
        encoding="utf-8",
    )
    methods = "_ALL_METHODS" if compat_get else "_CAMPAIGN_WRITE_METHODS"
    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "_ALL_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']\n"
        "_CAMPAIGN_WRITE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']\n"
        f"@router.api_route('/api/admin/cloud-orchestrator/campaigns', methods={methods})\n"
        f"@router.api_route('/api/admin/cloud-orchestrator/campaigns/{{path:path}}', methods={methods})\n"
        "async def legacy_cloud_orchestrator_campaign_routes(request):\n"
        "    return None\n",
        encoding="utf-8",
    )
    api.write_text("def read():\n    return {'fallback_used': False, 'real_external_call_executed': False}\n", encoding="utf-8")
    read_model.write_text("def read():\n    return {'ok': True}\n", encoding="utf-8")


def test_cloud_orchestrator_campaign_read_closeout_guard_passes_current_repo() -> None:
    assert check_cloud_orchestrator_campaign_read_closeout_lock() == []


def test_cloud_orchestrator_campaign_write_commandbus_guard_passes_current_repo() -> None:
    assert check_cloud_orchestrator_campaign_write_next_commandbus() == []


def test_cloud_orchestrator_campaign_read_closeout_guard_blocks_rollback(tmp_path: Path) -> None:
    _write_cloud_campaign_read_docs(tmp_path, locked=False, compat_get=True)

    violations = check_cloud_orchestrator_campaign_read_closeout_lock(tmp_path)
    codes = {violation.code for violation in violations}

    assert "cloud_campaign_read_production_compat_get_route" in codes
    assert "cloud_campaign_read_registry_owner" in codes
    assert "cloud_campaign_read_registry_legacy_allowed" in codes
    assert "cloud_campaign_read_registry_rollback_lifecycle" in codes
    assert "cloud_campaign_read_manifest_legacy_allowed" in codes
    assert "cloud_campaign_read_manifest_legacy_forward" in codes
    assert "cloud_campaign_read_manifest_rollback_lifecycle" in codes


def _write_media_library_docs(tmp_path: Path, *, locked: bool = True) -> None:
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory = tmp_path / "docs/architecture/media_library_route_inventory.md"
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    legacy_allowed = "false" if locked else "true"
    legacy_source = '""' if locked else "production_compat"
    delete_status = "deletion_locked" if locked else "next_primary_with_legacy_rollback"
    replacement_status = "locked" if locked else "validating"
    page_owner = "frontend_compat over Next APIs" if locked else "production_compat"
    read_owner = "next_native" if locked else "production_compat"
    command_owner = "next_storage_adapter" if locked else "production_compat"
    manifest_page_owner = "frontend_compat" if locked else "production_compat"
    manifest_api_owner = "next" if locked else "production_compat"
    manifest_behavior = "fake_adapter" if locked else "legacy_forward"
    delete_ready = "true" if locked else "false"

    registry.write_text(
        "routes:\n"
        "  - route_id: media_library_admin_pages_family\n"
        "    path_pattern: /admin/*-library\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {page_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: none\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: media_library_image_read_family\n"
        "    path_pattern: /api/admin/image-library*\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {read_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: local\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: media_library_image_command_family\n"
        "    path_pattern: /api/admin/image-library*\n"
        "    methods: [POST, PUT, DELETE, OPTIONS]\n"
        f"    runtime_owner: {command_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: local / fake / real_blocked\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: media_library_attachment_read_family\n"
        "    path_pattern: /api/admin/attachment-library*\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {read_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: local\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: media_library_attachment_command_family\n"
        "    path_pattern: /api/admin/attachment-library*\n"
        "    methods: [POST, PUT, DELETE, OPTIONS]\n"
        f"    runtime_owner: {command_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: local / fake / real_blocked\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: media_library_miniprogram_read_family\n"
        "    path_pattern: /api/admin/miniprogram-library*\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {read_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: local\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "  - route_id: media_library_miniprogram_command_family\n"
        "    path_pattern: /api/admin/miniprogram-library*\n"
        "    methods: [POST, PUT, DELETE, OPTIONS]\n"
        f"    runtime_owner: {command_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    legacy_source: {legacy_source}\n"
        "    adapter_mode: local / fake / real_blocked\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /admin/image-library\n"
        "    methods: [GET]\n"
        f"    current_runtime_owner: {manifest_page_owner}\n"
        "    production_behavior: readonly_facade\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: page shell no external call\n"
        "  - route_pattern: /admin/attachment-library\n"
        "    methods: [GET]\n"
        f"    current_runtime_owner: {manifest_page_owner}\n"
        "    production_behavior: readonly_facade\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: page shell no external call\n"
        "  - route_pattern: /admin/miniprogram-library\n"
        "    methods: [GET]\n"
        f"    current_runtime_owner: {manifest_page_owner}\n"
        "    production_behavior: readonly_facade\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: page shell no external call\n"
        "  - route_pattern: /api/admin/image-library*\n"
        "    methods: [GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD]\n"
        f"    current_runtime_owner: {manifest_api_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: no real external storage and no real WeCom media upload\n"
        "  - route_pattern: /api/admin/image-library/upload\n"
        "    methods: [POST, OPTIONS]\n"
        f"    current_runtime_owner: {manifest_api_owner}\n"
        "    production_behavior: guarded_preview\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: no real external storage and no real WeCom media upload\n"
        "  - route_pattern: /api/admin/attachment-library*\n"
        "    methods: [GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD]\n"
        f"    current_runtime_owner: {manifest_api_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: no real external storage and no real WeCom media upload\n"
        "  - route_pattern: /api/admin/miniprogram-library*\n"
        "    methods: [GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD]\n"
        f"    current_runtime_owner: {manifest_api_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        f"    delete_ready: {delete_ready}\n"
        f"    delete_status: {delete_status}\n"
        f"    replacement_status: {replacement_status}\n"
        "    notes: no real external storage and no real WeCom media upload\n",
        encoding="utf-8",
    )
    inventory.write_text(
        "# Media Library Route Inventory\n\n"
        "## Frontend ↔ API ↔ Backend Contract Matrix\n\n"
        "Media Library production_compat rollback is removed; legacy_fallback_allowed=false; deletion_locked; "
        "real_external_call_executed=false.\n\n"
        "- Real external object storage enablement.\n"
        "- Real WeCom media upload.\n",
        encoding="utf-8",
    )


def test_media_library_guard_flags_legacy_and_external_drift(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    media_api = tmp_path / "aicrm_next/media_library/api.py"
    compat.parent.mkdir(parents=True)
    media_api.parent.mkdir(parents=True)
    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/admin/image-library/upload', methods=['POST'])\n"
        "def legacy_image_upload(): pass\n",
        encoding="utf-8",
    )
    media_api.write_text(
        "import requests\n"
        "def image_from_url():\n"
        "    requests.get('https://example.invalid/test.png')\n"
        "    return {'real_external_call_executed': True}\n",
        encoding="utf-8",
    )
    _write_media_library_docs(tmp_path, locked=False)

    codes = {violation.code for violation in check_media_library_closeout_lock(tmp_path)}

    assert "media_library_production_compat_route" in codes
    assert "media_library_direct_http_client" in codes
    assert "media_library_real_external_call_true" in codes
    assert "media_library_registry_legacy_allowed" in codes
    assert "media_library_registry_legacy_source" in codes
    assert "media_library_registry_lifecycle" in codes
    assert "media_library_manifest_owner" in codes
    assert "media_library_manifest_legacy_allowed" in codes
    assert "media_library_manifest_legacy_forward" in codes
    assert "media_library_manifest_lifecycle" in codes


def test_media_library_guard_allows_locked_next_routes(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    media_api = tmp_path / "aicrm_next/media_library/api.py"
    compat.parent.mkdir(parents=True)
    media_api.parent.mkdir(parents=True)
    compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8")
    media_api.write_text(
        "def list_images():\n"
        "    return {'fallback_used': False, 'real_external_call_executed': False}\n",
        encoding="utf-8",
    )
    _write_media_library_docs(tmp_path, locked=True)

    assert check_media_library_closeout_lock(tmp_path) == []


def test_questionnaire_h5_submit_guard_flags_legacy_route_and_lifecycle_drift(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/questionnaire/api.py"
    h5_write = tmp_path / "aicrm_next/questionnaire/h5_write.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

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
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

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


def test_sidebar_jssdk_guard_flags_legacy_forward_and_direct_http_drift(tmp_path: Path) -> None:
    inventory = tmp_path / "docs/architecture/sidebar_jssdk_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/identity_contact/sidebar_jssdk.py"
    adapter = tmp_path / "aicrm_next/integration_gateway/wecom_jssdk_adapter.py"
    main = tmp_path / "aicrm_next/main.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory.parent.mkdir(parents=True)
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    adapter.parent.mkdir(parents=True)
    main.parent.mkdir(parents=True, exist_ok=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    inventory.write_text(
        "Frontend ↔ API ↔ Backend Contract Matrix\n"
        "/sidebar/bind-mobile sidebar_customer_workbench.html sidebar_workbench.js /api/sidebar/jssdk-config\n"
        "url debug agentid ok appId corpId timestamp nonceStr signature jsApiList source_status adapter_mode route_owner fallback_used real_external_call_executed\n",
        encoding="utf-8",
    )
    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/sidebar/jssdk-config', methods=['GET', 'HEAD', 'OPTIONS'])\n"
        "def legacy_jssdk():\n"
        "    pass\n",
        encoding="utf-8",
    )
    api.write_text(
        "def sidebar_jssdk_config():\n"
        "    return forward_to_legacy_flask()\n"
        "HEAD = 'HEAD'\n"
        "OPTIONS = 'OPTIONS'\n"
        "build_sidebar_jssdk_config = object\n",
        encoding="utf-8",
    )
    adapter.write_text(
        "class ExternalCallAttempt: pass\n"
        "def build_sidebar_jssdk_config():\n"
        "    return requests.post('https://example.com')\n"
        "def record_event(): pass\n"
        "real_external_call_executed = False\n",
        encoding="utf-8",
    )
    compat_router_name = "production_compat" + "_router"
    main.write_text(f"{compat_router_name} = object\nsidebar_jssdk_router = object\n", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/sidebar/jssdk-config\n"
        "    methods: [GET, HEAD, OPTIONS]\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    legacy_source: production_compat\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/sidebar/jssdk-config\n"
        "    methods: [GET, HEAD, OPTIONS]\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_ready: false\n"
        "    adapter_mode: real_enabled\n"
        "    delete_status: next_primary_with_legacy_rollback\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )

    codes = {violation.code for violation in check_sidebar_jssdk_next_adapter(tmp_path)}

    assert "sidebar_jssdk_production_compat_route" in codes
    assert "sidebar_jssdk_legacy_forward" in codes
    assert "sidebar_jssdk_direct_http_client" in codes
    assert "sidebar_jssdk_router_order" in codes
    assert "sidebar_jssdk_registry_owner" in codes
    assert "sidebar_jssdk_registry_legacy_allowed" in codes
    assert "sidebar_jssdk_registry_legacy_source" in codes
    assert "sidebar_jssdk_registry_lifecycle" in codes
    assert "sidebar_jssdk_registry_rollback_lifecycle" in codes
    assert "sidebar_jssdk_manifest_owner" in codes
    assert "sidebar_jssdk_manifest_behavior" in codes
    assert "sidebar_jssdk_manifest_legacy_allowed" in codes
    assert "sidebar_jssdk_manifest_delete_ready" in codes
    assert "sidebar_jssdk_manifest_rollback_lifecycle" in codes


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


def test_questionnaire_admin_write_guard_allows_locked_next_commandbus(tmp_path: Path) -> None:
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

    compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8")
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
        "    current_runtime_owner: next_adapter\n"
        "    production_behavior: next_adapter\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n",
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
        f"app.include_router({'production_compat' + '_router'})\n"
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
        f"app.include_router({'production_compat' + '_router'})\n",
        encoding="utf-8",
    )
    _write_wecom_tag_read_docs(tmp_path)

    assert check_wecom_tag_read_next_native(tmp_path) == []


def _write_automation_timer_guard_fixture(tmp_path: Path, *, locked: bool) -> None:
    inventory = tmp_path / "docs/architecture/automation_conversion_timer_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/automation_engine/api.py"
    timer_module = tmp_path / "aicrm_next/automation_engine/timers.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory.parent.mkdir(parents=True)
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    inventory.write_text(
        "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix\n"
        "PlanReplyMonitorCaptureCommand PlanReplyMonitorRunDueCommand PreviewAutomationJobsRunDueCommand PlanAutomationJobsRunDueCommand\n"
        "legacy_fallback_allowed=false deletion_locked adapter_mode=real_blocked real_external_call_executed=false automation_runtime_executed=false wecom_send_executed=false\n"
        "next_reply_monitor_capture_plan next_reply_monitor_run_due_plan next_jobs_run_due_preview next_jobs_run_due_plan\n"
        "/api/admin/automation-conversion/reply-monitor/capture\n"
        "/api/admin/automation-conversion/reply-monitor/run-due\n"
        "/api/admin/automation-conversion/jobs/run-due/preview\n"
        "/api/admin/automation-conversion/jobs/run-due\n"
        "/api/admin/automation-conversion/tasks/run-due send-via-bazhuayu\n",
        encoding="utf-8",
    )
    compat_routes = (
        "@router.api_route('/api/admin/automation-conversion/reply-monitor/capture', methods=['POST'])\n"
        "def rollback(): pass\n"
        if not locked
        else ""
    )
    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        f"{compat_routes}"
        "@router.api_route('/api/admin/automation-conversion/tasks/run-due', methods=['POST', 'OPTIONS'])\n"
        "def tasks(): pass\n"
        "@router.api_route('/api/admin/automation-conversion/execution-items/{execution_item_id:int}/send-via-bazhuayu', methods=['POST', 'OPTIONS'])\n"
        "def send_via(): pass\n",
        encoding="utf-8",
    )
    api.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/admin/automation-conversion/reply-monitor/capture')\n"
        "def api_plan_automation_conversion_reply_monitor_capture(): return execute_automation_timer_command()\n"
        "@router.post('/api/admin/automation-conversion/reply-monitor/run-due')\n"
        "def api_plan_automation_conversion_reply_monitor_run_due(): return execute_automation_timer_command()\n"
        "@router.post('/api/admin/automation-conversion/jobs/run-due/preview')\n"
        "def api_preview_automation_conversion_jobs_run_due(): return execute_automation_timer_command()\n"
        "@router.post('/api/admin/automation-conversion/jobs/run-due')\n"
        "def api_plan_automation_conversion_jobs_run_due(): return execute_automation_timer_command()\n",
        encoding="utf-8",
    )
    timer_module.write_text(
        "PlanReplyMonitorCaptureCommand PlanReplyMonitorRunDueCommand PreviewAutomationJobsRunDueCommand PlanAutomationJobsRunDueCommand\n"
        "InMemoryAuditLedger InMemorySideEffectPlanRepository InMemoryExternalCallAttemptRepository CommandBus\n"
        "next_reply_monitor_capture_plan next_reply_monitor_run_due_plan next_jobs_run_due_preview next_jobs_run_due_plan\n"
        "real_blocked automation_runtime_executed wecom_send_executed\n"
        + ("run_reply_monitor_capture\n" if not locked else ""),
        encoding="utf-8",
    )
    registry_owner = "next_runtime_plan" if locked else "production_compat"
    registry_legacy = "false" if locked else "true"
    manifest_behavior = "next_command" if locked else "scheduled_safe_mode"
    manifest_delete_ready = "true" if locked else "false"
    registry.write_text(
        "routes:\n"
        "  - route_id: automation_conversion_reply_monitor_timer_next_safe_mode\n"
        "    path_pattern: /api/admin/automation-conversion/reply-monitor*\n"
        "    methods: [POST, OPTIONS]\n"
        "    runtime_owner: " + registry_owner + "\n"
        "    legacy_fallback_allowed: " + registry_legacy + "\n"
        "    legacy_source: \"\"\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_id: automation_conversion_jobs_run_due_timer_next_safe_mode\n"
        "    path_pattern: /api/admin/automation-conversion/jobs/run-due*\n"
        "    methods: [POST, OPTIONS]\n"
        "    runtime_owner: " + registry_owner + "\n"
        "    legacy_fallback_allowed: " + registry_legacy + "\n"
        "    legacy_source: \"\"\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/automation-conversion/reply-monitor*\n"
        "    methods: [POST, OPTIONS]\n"
        "    current_runtime_owner: " + registry_owner + "\n"
        "    production_behavior: " + manifest_behavior + "\n"
        "    legacy_fallback_allowed: " + registry_legacy + "\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_ready: " + manifest_delete_ready + "\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - route_pattern: /api/admin/automation-conversion/jobs/run-due*\n"
        "    methods: [POST, OPTIONS]\n"
        "    current_runtime_owner: " + registry_owner + "\n"
        "    production_behavior: " + manifest_behavior + "\n"
        "    legacy_fallback_allowed: " + registry_legacy + "\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        "    delete_ready: " + manifest_delete_ready + "\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n",
        encoding="utf-8",
    )


def test_automation_timer_guard_flags_rollback_and_runtime_drift(tmp_path: Path) -> None:
    _write_automation_timer_guard_fixture(tmp_path, locked=False)

    codes = {violation.code for violation in check_automation_conversion_timers_next_safe_mode(tmp_path)}

    assert "automation_timer_production_compat_rollback" in codes
    assert "automation_timer_legacy_capture_runtime" in codes
    assert "automation_timer_registry_owner" in codes
    assert "automation_timer_registry_legacy_allowed" in codes
    assert "automation_timer_manifest_behavior" in codes
    assert "automation_timer_manifest_legacy_allowed" in codes


def test_automation_timer_guard_allows_next_safe_mode_locked(tmp_path: Path) -> None:
    _write_automation_timer_guard_fixture(tmp_path, locked=True)

    assert check_automation_conversion_timers_next_safe_mode(tmp_path) == []


def _write_automation_workspace_runtime_guard_fixture(tmp_path: Path, *, locked: bool) -> None:
    inventory = tmp_path / "docs/architecture/automation_workspace_runtime_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/automation_engine/api.py"
    runtime_module = tmp_path / "aicrm_next/automation_engine/workspace_runtime.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory.parent.mkdir(parents=True)
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    inventory.write_text(
        "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix\n"
        "PlanAutomationOperationTasksRunDueCommand PlanAutomationExecutionItemBazhuayuDispatchCommand\n"
        "legacy_fallback_allowed=false deletion_locked adapter_mode=real_blocked\n"
        "real_external_call_executed=false automation_runtime_executed=false operation_tasks_executed=false\n"
        "bazhuayu_send_executed=false wecom_send_executed=false\n"
        "next_automation_tasks_run_due_plan next_bazhuayu_dispatch_plan\n"
        "member/manual/focus/SOP customer automation webhooks\n"
        "/api/admin/automation-conversion/tasks/run-due\n"
        "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu\n",
        encoding="utf-8",
    )
    compat_routes = (
        "@router.api_route('/api/admin/automation-conversion/tasks/run-due', methods=['POST', 'OPTIONS'])\n"
        "def tasks(): pass\n"
        "@router.api_route('/api/admin/automation-conversion/execution-items/{execution_item_id:int}/send-via-bazhuayu', methods=['POST', 'OPTIONS'])\n"
        "def send_via(): pass\n"
        if not locked
        else ""
    )
    compat.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        f"{compat_routes}",
        encoding="utf-8",
    )
    api.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.options('/api/admin/automation-conversion/tasks/run-due')\n"
        "def api_automation_workspace_tasks_run_due_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/tasks/run-due')\n"
        "def api_plan_automation_workspace_tasks_run_due(): return execute_workspace_runtime_command()\n"
        "@router.options('/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu')\n"
        "def api_automation_workspace_execution_item_outbound_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu')\n"
        "def api_plan_automation_workspace_execution_item_outbound(): return execute_workspace_runtime_command()\n",
        encoding="utf-8",
    )
    runtime_module.write_text(
        "PlanAutomationOperationTasksRunDueCommand PlanAutomationExecutionItemOutboundDispatchCommand\n"
        "InMemoryAuditLedger InMemorySideEffectPlanRepository InMemoryExternalCallAttemptRepository CommandBus\n"
        "next_automation_tasks_run_due_plan next_bazhuayu_dispatch_plan real_blocked\n"
        "operation_tasks_executed bazhuayu_send_executed wecom_send_executed\n"
        + ("run_due_operation_tasks\n" if not locked else ""),
        encoding="utf-8",
    )
    registry_owner = "next_runtime_plan" if locked else "production_compat"
    legacy_allowed = "false" if locked else "true"
    manifest_behavior = "next_command" if locked else "legacy_forward"
    lifecycle = "deletion_locked" if locked else "next_primary_with_legacy_rollback"
    replacement = "locked" if locked else "validating"
    registry.write_text(
        "routes:\n"
        "  - route_id: automation_workspace_tasks_run_due_next_safe_mode\n"
        "    path_pattern: /api/admin/automation-conversion/tasks/run-due\n"
        "    methods: [POST, OPTIONS]\n"
        f"    runtime_owner: {registry_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    legacy_source: \"\"\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n"
        "  - route_id: automation_workspace_execution_item_bazhuayu_next_safe_mode\n"
        "    path_pattern: /api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu\n"
        "    methods: [POST, OPTIONS]\n"
        f"    runtime_owner: {registry_owner}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    legacy_source: \"\"\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/automation-conversion/tasks/run-due\n"
        "    methods: [POST, OPTIONS]\n"
        f"    current_runtime_owner: {registry_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n"
        "  - route_pattern: /api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu\n"
        "    methods: [POST, OPTIONS]\n"
        f"    current_runtime_owner: {registry_owner}\n"
        f"    production_behavior: {manifest_behavior}\n"
        f"    legacy_fallback_allowed: {legacy_allowed}\n"
        "    external_side_effect_risk: high\n"
        "    adapter_mode: real_blocked\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n",
        encoding="utf-8",
    )


def test_automation_workspace_runtime_guard_flags_rollback_and_runtime_drift(tmp_path: Path) -> None:
    _write_automation_workspace_runtime_guard_fixture(tmp_path, locked=False)

    codes = {violation.code for violation in check_automation_workspace_runtime_next_safe_mode(tmp_path)}

    assert "automation_workspace_production_compat_rollback" in codes
    assert "automation_workspace_legacy_operation_task_runtime" in codes
    assert "automation_workspace_registry_owner" in codes
    assert "automation_workspace_registry_legacy_allowed" in codes
    assert "automation_workspace_manifest_behavior" in codes
    assert "automation_workspace_manifest_legacy_allowed" in codes


def test_automation_workspace_runtime_guard_allows_next_safe_mode_locked(tmp_path: Path) -> None:
    _write_automation_workspace_runtime_guard_fixture(tmp_path, locked=True)

    assert check_automation_workspace_runtime_next_safe_mode(tmp_path) == []


def test_audience_transition_imports_are_not_wecom_allowlisted() -> None:
    import scripts.check_no_new_legacy as checker

    audience_transition_paths = {
        Path("aicrm_next/automation_engine/audience_transition/repository.py"),
        Path("aicrm_next/automation_engine/audience_transition/integration_gateway.py"),
        Path("aicrm_next/automation_engine/audience_transition/application.py"),
    }

    assert checker.WECOM_IMPORT_ALLOWLIST.isdisjoint(audience_transition_paths)


def _write_automation_member_actions_guard_fixture(tmp_path: Path, *, locked: bool) -> None:
    inventory = tmp_path / "docs/architecture/automation_member_actions_route_inventory.md"
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    api = tmp_path / "aicrm_next/automation_engine/api.py"
    module = tmp_path / "aicrm_next/automation_engine/member_actions.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    inventory.parent.mkdir(parents=True)
    compat.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    action_routes = [
        "/api/admin/automation-conversion/member/put-in-pool",
        "/api/admin/automation-conversion/member/remove-from-pool",
        "/api/admin/automation-conversion/member/set-focus",
        "/api/admin/automation-conversion/member/set-normal",
        "/api/admin/automation-conversion/member/mark-won",
        "/api/admin/automation-conversion/member/unmark-won",
        "/api/admin/automation-conversion/member/push-openclaw",
    ]
    inventory.write_text(
        "Frontend ↔ API ↔ Backend Contract Matrix\n"
        "GetAutomationMemberDetailQuery PutAutomationMemberInPoolCommand RemoveAutomationMemberFromPoolCommand\n"
        "SetAutomationMemberFocusCommand SetAutomationMemberNormalCommand MarkAutomationMemberWonCommand\n"
        "UnmarkAutomationMemberWonCommand PlanAutomationMemberOpenClawPushCommand\n"
        "legacy_fallback_allowed=false deletion_locked adapter_mode=real_blocked\n"
        "real_external_call_executed=false automation_runtime_executed=false openclaw_push_executed=false\n"
        "stage manual-send focus-send-batches SOP customer automation webhook\n"
        "/api/admin/automation-conversion/member\n"
        + "\n".join(action_routes)
        + "\n",
        encoding="utf-8",
    )
    compat_routes = (
        "@router.api_route('/api/admin/automation-conversion/member', methods=['GET', 'HEAD'])\n"
        "def detail(): pass\n"
        "@router.api_route('/api/admin/automation-conversion/member/{path:path}', methods=['GET', 'POST', 'OPTIONS'])\n"
        "def wildcard(): pass\n"
        if not locked
        else ""
    )
    compat.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n" + compat_routes, encoding="utf-8")
    api.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.api_route('/api/admin/automation-conversion/member', methods=['GET', 'HEAD'])\n"
        "def api_automation_member_detail(): return read_automation_member_detail()\n"
        "@router.options('/api/admin/automation-conversion/member/put-in-pool')\n"
        "def api_automation_member_put_in_pool_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/put-in-pool')\n"
        "def api_plan_automation_member_put_in_pool(): return execute_member_action_command()\n"
        "@router.options('/api/admin/automation-conversion/member/remove-from-pool')\n"
        "def api_automation_member_remove_from_pool_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/remove-from-pool')\n"
        "def api_plan_automation_member_remove_from_pool(): return execute_member_action_command()\n"
        "@router.options('/api/admin/automation-conversion/member/set-focus')\n"
        "def api_automation_member_set_focus_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/set-focus')\n"
        "def api_plan_automation_member_set_focus(): return execute_member_action_command()\n"
        "@router.options('/api/admin/automation-conversion/member/set-normal')\n"
        "def api_automation_member_set_normal_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/set-normal')\n"
        "def api_plan_automation_member_set_normal(): return execute_member_action_command()\n"
        "@router.options('/api/admin/automation-conversion/member/mark-won')\n"
        "def api_automation_member_mark_won_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/mark-won')\n"
        "def api_plan_automation_member_mark_won(): return execute_member_action_command()\n"
        "@router.options('/api/admin/automation-conversion/member/unmark-won')\n"
        "def api_automation_member_unmark_won_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/unmark-won')\n"
        "def api_plan_automation_member_unmark_won(): return execute_member_action_command()\n"
        "@router.options('/api/admin/automation-conversion/member/push-openclaw')\n"
        "def api_automation_member_push_openclaw_options(): return {}\n"
        "@router.post('/api/admin/automation-conversion/member/push-openclaw')\n"
        "def api_plan_automation_member_push_openclaw(): return execute_member_action_command()\n",
        encoding="utf-8",
    )
    module.write_text(
        "GetAutomationMemberDetailQuery PutAutomationMemberInPoolCommand RemoveAutomationMemberFromPoolCommand\n"
        "SetAutomationMemberFocusCommand SetAutomationMemberNormalCommand MarkAutomationMemberWonCommand\n"
        "UnmarkAutomationMemberWonCommand PlanAutomationMemberOpenClawPushCommand\n"
        "InMemoryAuditLedger InMemorySideEffectPlanRepository InMemoryExternalCallAttemptRepository CommandBus\n"
        "next_automation_member_read next_command real_blocked openclaw_push_executed\n"
        + ("legacy_automation_facade\n" if not locked else ""),
        encoding="utf-8",
    )
    owner = "next_read_model" if locked else "production_compat"
    command_owner = "next_command" if locked else "production_compat"
    fallback = "false" if locked else "true"
    behavior = "next_command" if locked else "legacy_forward"
    lifecycle = "deletion_locked" if locked else "next_primary_with_legacy_rollback"
    replacement = "locked" if locked else "validating"
    registry.write_text(
        "routes:\n"
        "  - route_id: automation_member_detail_next_read_model\n"
        "    path_pattern: /api/admin/automation-conversion/member\n"
        "    methods: [GET, HEAD]\n"
        f"    runtime_owner: {owner}\n"
        f"    legacy_fallback_allowed: {fallback}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n"
        + "".join(
            "  - route_id: " + route_id + "\n"
            "    path_pattern: " + route + "\n"
            "    methods: [POST, OPTIONS]\n"
            f"    runtime_owner: {command_owner}\n"
            f"    legacy_fallback_allowed: {fallback}\n"
            f"    external_side_effect_risk: {'high' if route_id == 'automation_member_push_openclaw_next_command' else 'medium'}\n"
            "    adapter_mode: real_blocked\n"
            f"    delete_status: {lifecycle}\n"
            f"    replacement_status: {replacement}\n"
            for route_id, route in {
                "automation_member_put_in_pool_next_command": "/api/admin/automation-conversion/member/put-in-pool",
                "automation_member_remove_from_pool_next_command": "/api/admin/automation-conversion/member/remove-from-pool",
                "automation_member_set_focus_next_command": "/api/admin/automation-conversion/member/set-focus",
                "automation_member_set_normal_next_command": "/api/admin/automation-conversion/member/set-normal",
                "automation_member_mark_won_next_command": "/api/admin/automation-conversion/member/mark-won",
                "automation_member_unmark_won_next_command": "/api/admin/automation-conversion/member/unmark-won",
                "automation_member_push_openclaw_next_command": "/api/admin/automation-conversion/member/push-openclaw",
            }.items()
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/automation-conversion/member\n"
        "    methods: [GET, HEAD]\n"
        f"    current_runtime_owner: {owner}\n"
        f"    production_behavior: {'next_exact' if locked else 'legacy_forward'}\n"
        f"    legacy_fallback_allowed: {fallback}\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n"
        + "".join(
            "  - route_pattern: " + route + "\n"
            "    methods: [POST, OPTIONS]\n"
            f"    current_runtime_owner: {command_owner}\n"
            f"    production_behavior: {behavior}\n"
            f"    legacy_fallback_allowed: {fallback}\n"
            "    adapter_mode: real_blocked\n"
            f"    delete_status: {lifecycle}\n"
            f"    replacement_status: {replacement}\n"
            for route in action_routes
        ),
        encoding="utf-8",
    )


def test_automation_member_actions_guard_flags_rollback_and_legacy_drift(tmp_path: Path) -> None:
    _write_automation_member_actions_guard_fixture(tmp_path, locked=False)

    codes = {violation.code for violation in check_automation_member_actions_next_safe_mode(tmp_path)}

    assert "automation_member_production_compat_rollback" in codes
    assert "automation_member_legacy_facade" in codes
    assert "automation_member_registry_owner" in codes
    assert "automation_member_registry_legacy_allowed" in codes
    assert "automation_member_manifest_behavior" in codes
    assert "automation_member_manifest_legacy_allowed" in codes


def test_automation_member_actions_guard_allows_next_safe_mode_locked(tmp_path: Path) -> None:
    _write_automation_member_actions_guard_fixture(tmp_path, locked=True)

    assert check_automation_member_actions_next_safe_mode(tmp_path) == []


def _write_automation_overview_pools_guard_fixture(tmp_path: Path, *, locked: bool) -> None:
    api = tmp_path / "aicrm_next/automation_engine/api.py"
    module = tmp_path / "aicrm_next/automation_engine/overview_read_model.py"
    facade = tmp_path / "aicrm_next/integration_gateway/legacy_automation_facade.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    api.parent.mkdir(parents=True)
    facade.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    legacy_branch = (
        "from aicrm_next.integration_gateway.legacy_automation_facade import get_automation_overview_from_legacy\n"
        "from aicrm_next.shared.runtime import production_data_ready\n"
        "if production_data_ready(): return get_automation_overview_from_legacy()\n"
        if not locked
        else ""
    )
    api.write_text(
        "from fastapi import APIRouter\n"
        "from starlette.responses import JSONResponse\n"
        "from aicrm_next.automation_engine.overview_read_model import AutomationOverviewReadModel, AutomationPoolReadModel\n"
        "router = APIRouter()\n"
        "@router.get('/api/admin/automation-conversion/overview')\n"
        "def overview():\n"
        f"    {legacy_branch if legacy_branch else 'return JSONResponse(AutomationOverviewReadModel().execute(), headers={\"X-AICRM-Fallback-Used\": \"false\"})'}\n"
        "@router.get('/api/admin/automation-conversion/pools')\n"
        "def pools():\n"
        "    return JSONResponse(AutomationPoolReadModel().execute(), headers={'X-AICRM-Fallback-Used': 'false'})\n",
        encoding="utf-8",
    )
    module.write_text(
        "class AutomationOverviewReadModel: pass\n"
        "class AutomationPoolReadModel: pass\n"
        "class AutomationStageColumnProjection: pass\n"
        "automation_member stage_columns focus_count normal_count today_new_count source_status next_read_model\n",
        encoding="utf-8",
    )
    facade.write_text(
        ("def get_automation_overview_from_legacy(): pass\n" "def list_automation_pools_from_legacy(): pass\n" if not locked else ""),
        encoding="utf-8",
    )
    owner = "next_read_model" if locked else "production_compat"
    fallback = "false" if locked else "true"
    behavior = "next_exact" if locked else "legacy_forward"
    lifecycle = "deletion_locked" if locked else "next_primary_with_legacy_rollback"
    replacement = "locked" if locked else "validating"
    registry.write_text(
        "routes:\n"
        "  - route_id: automation_conversion_overview_next_read_model\n"
        "    path_pattern: /api/admin/automation-conversion/overview\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {owner}\n"
        f"    legacy_fallback_allowed: {fallback}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n"
        "  - route_id: automation_conversion_pools_next_read_model\n"
        "    path_pattern: /api/admin/automation-conversion/pools\n"
        "    methods: [GET]\n"
        f"    runtime_owner: {owner}\n"
        f"    legacy_fallback_allowed: {fallback}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/admin/automation-conversion/overview\n"
        "    methods: [GET]\n"
        f"    current_runtime_owner: {owner}\n"
        f"    production_behavior: {behavior}\n"
        f"    legacy_fallback_allowed: {fallback}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n"
        "  - route_pattern: /api/admin/automation-conversion/pools\n"
        "    methods: [GET]\n"
        f"    current_runtime_owner: {owner}\n"
        f"    production_behavior: {behavior}\n"
        f"    legacy_fallback_allowed: {fallback}\n"
        "    external_side_effect_risk: none\n"
        f"    delete_status: {lifecycle}\n"
        f"    replacement_status: {replacement}\n",
        encoding="utf-8",
    )


def test_automation_overview_pools_guard_flags_legacy_drift(tmp_path: Path) -> None:
    _write_automation_overview_pools_guard_fixture(tmp_path, locked=False)

    codes = {violation.code for violation in check_automation_overview_pools_next_read_model(tmp_path)}

    assert "automation_overview_api_legacy_marker" in codes
    assert "automation_overview_deleted_facade_function" in codes
    assert "automation_overview_registry_owner" in codes
    assert "automation_overview_registry_legacy_allowed" in codes
    assert "automation_overview_manifest_behavior" in codes
    assert "automation_overview_manifest_legacy_allowed" in codes


def test_automation_overview_pools_guard_allows_next_read_model_locked(tmp_path: Path) -> None:
    _write_automation_overview_pools_guard_fixture(tmp_path, locked=True)

    assert check_automation_overview_pools_next_read_model(tmp_path) == []
