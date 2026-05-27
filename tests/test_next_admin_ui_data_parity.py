from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.frontend_compat.legacy_routes import ADMIN_NAV_GROUPS
from aicrm_next.main import create_app
from tools import check_next_admin_ui_data_parity as checker


def test_next_shell_context_returns_target_grouped_navigation(monkeypatch):
    client = _client(monkeypatch)

    payload = client.get("/api/admin/dashboard/shell-context").json()

    assert payload["ok"] is True
    assert [(group["title"], [item["label"] for item in group["items"]]) for group in payload["nav_groups"]] == checker.TARGET_NAV_GROUPS


def test_next_admin_base_shell_renders_grouped_sidebar_and_active_item(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/automation-conversion")
    html = response.text

    assert response.status_code == 200
    for group_title, labels in checker.TARGET_NAV_GROUPS:
        assert group_title in html
        for label in labels:
            assert label in html
    assert 'class="admin-nav-link is-active"' in html
    assert ">自动化运营<" in html
    assert "User Ops" not in html
    assert "fixture adapter" not in html.lower()
    assert "partial adapter" not in html.lower()


def test_target_admin_pages_are_not_404(monkeypatch):
    client = _client(monkeypatch)

    for route in checker.ADMIN_PAGES:
        response = client.get(route, follow_redirects=False)
        assert response.status_code != 404, route


def test_next_customer_detail_route_renders_profile_page_instead_of_json_redirect(monkeypatch):
    client = _client(monkeypatch)

    list_response = client.get("/admin/customers")
    detail_response = client.get("/admin/customers/wx_ext_001?tab=messages", follow_redirects=False)
    html = detail_response.text

    assert list_response.status_code == 200
    assert 'href="/admin/customers/wx_ext_001"' in list_response.text
    assert "/api/admin/customers/profile?external_userid=wx_ext_001" not in list_response.text
    assert detail_response.status_code == 200
    assert "text/html" in detail_response.headers["content-type"]
    assert "客户档案" in html
    assert "实时标签" in html
    assert "已填写问卷及答案" in html
    assert "聊天记录" in html
    assert "自动化转化" in html
    assert 'data-initial-section="customer-message-records"' in html
    assert detail_response.headers.get("location", "") == ""


def test_next_customer_profile_section_apis_are_native_readonly_routes(monkeypatch):
    client = _client(monkeypatch)

    questionnaire_response = client.get("/api/admin/customers/profile/questionnaire-answers?external_userid=wx_ext_001")
    messages_response = client.get("/api/admin/customers/profile/messages?external_userid=wx_ext_001")

    assert questionnaire_response.status_code == 200
    assert questionnaire_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert questionnaire_response.json()["route_owner"] == "ai_crm_next"
    assert "answers" in questionnaire_response.json()
    assert messages_response.status_code == 200
    assert messages_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert messages_response.json()["route_owner"] == "ai_crm_next"
    assert "messages" in messages_response.json()


def test_next_channels_page_is_first_level_sidebar_entry(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/channels")
    html = response.text

    assert response.status_code == 200
    assert "渠道码中心" in html
    assert "群运营计划" in html
    assert 'href="/admin/channels"' in html
    assert 'class="admin-nav-link is-active"' in html
    assert "渠道码中心只管理渠道资产" in html
    assert "/api/admin/channels?limit=300" in html
    assert "channel_code_center_next.js" in html


def test_next_channels_page_stays_next_owned_in_production_data_mode(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    client = _client(monkeypatch)
    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)

    async def fail_forward(_request):
        raise AssertionError("channels page should not forward to legacy Flask")

    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fail_forward)

    response = client.get("/admin/channels")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "渠道码中心" in response.text
    assert "群运营计划" in response.text


def test_next_wechat_transactions_page_uses_unified_admin_shell(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/wechat-pay/transactions")
    html = response.text

    assert response.status_code == 200
    assert 'data-next-commerce-admin="wechat-pay-transactions"' in html
    assert "admin-shell" in html
    assert "admin-nav" in html
    assert "群运营计划" in html
    assert "渠道码中心" in html
    assert "交易管理" in html
    assert "导出筛选结果" in html
    assert 'class="layout"' not in html
    assert 'class="sidebar"' not in html
    assert "心流商业客户管理" not in html


def test_next_wechat_transaction_detail_page_uses_unified_admin_shell(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/wechat-pay/transactions/order_masked_001")
    html = response.text

    assert response.status_code == 200
    assert "admin-shell" in html
    assert "申请退款" in html
    assert "再次完整输入微信单号" in html
    assert "群运营计划" in html


def test_next_channel_form_pages_render_native_editor(monkeypatch):
    client = _client(monkeypatch)

    new_response = client.get("/admin/channels/new")

    assert new_response.status_code == 200
    new_html = new_response.text
    assert "新建渠道" in new_html
    assert "渠道名称" in new_html
    assert "欢迎语与素材" in new_html
    assert "预览并选择小程序" in new_html
    assert "Sunset / State" not in new_html
    assert "本地兼容层" not in new_html

    created = client.post(
        "/api/admin/channels",
        json={
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "channel_name": "测试获客链接",
            "channel_code": "test_link",
            "customer_channel": "wca_test_link",
            "link_url": "https://work.weixin.qq.com/ca/test",
            "welcome_message": "欢迎加入",
            "welcome_miniprogram_library_ids": [1],
            "welcome_attachment_library_ids": [2],
            "entry_tag_id": "tag_1",
            "entry_tag_name": "核心",
            "entry_tag_group_name": "客户等级",
        },
    )
    assert created.status_code == 201
    channel = created.json()["channel"]

    edit_response = client.get(f"/admin/channels/{channel['id']}/edit")

    assert edit_response.status_code == 200
    edit_html = edit_response.text
    assert "编辑渠道" in edit_html
    assert "测试获客链接" in edit_html
    assert "wca_test_link" in edit_html
    assert "欢迎加入" in edit_html
    assert "客户等级 / 核心" in edit_html
    assert "企微获客助手链接预览" in edit_html
    assert "channel_admission_pages.js" in edit_html
    assert "Sunset / State" not in edit_html
    assert "本地兼容层" not in edit_html


def test_next_channel_qrcode_patch_preserves_existing_scene_value(monkeypatch):
    client = _client(monkeypatch)

    created = client.post(
        "/api/admin/channels",
        json={
            "channel_type": "qrcode",
            "carrier_type": "qrcode",
            "channel_name": "测试二维码",
            "channel_code": "default_qrcode",
            "scene_value": "aqr_existing_state",
        },
    ).json()["channel"]

    updated = client.patch(
        f"/api/admin/channels/{created['id']}",
        json={
            "channel_type": "qrcode",
            "carrier_type": "qrcode",
            "channel_name": "测试二维码已编辑",
            "channel_code": "default_qrcode_edited",
            "welcome_message": "更新欢迎语",
        },
    )

    assert updated.status_code == 200
    channel = updated.json()["channel"]
    assert channel["channel_name"] == "测试二维码已编辑"
    assert channel["channel_code"] == "default_qrcode_edited"
    assert channel["scene_value"] == "aqr_existing_state"


def test_primary_admin_nav_pages_keep_next_shell_in_production_data_mode(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    client = _client(monkeypatch)
    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)

    async def fail_forward(_request):
        raise AssertionError("primary admin navigation pages should not forward to legacy Flask")

    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fail_forward)

    primary_routes = [
        "/admin/automation-conversion",
        "/admin/automation-conversion/group-ops/ui",
        "/admin/channels",
        "/admin/cloud-orchestrator/campaigns",
        "/admin/customers",
        "/admin/hxc-dashboard",
        "/admin/questionnaires",
        "/admin/wecom-tags",
        "/admin/wechat-pay/transactions",
        "/admin/wechat-pay/products",
        "/admin/image-library",
        "/admin/miniprogram-library",
        "/admin/attachment-library",
        "/admin/jobs",
        "/admin/config",
        "/admin/api-docs",
    ]
    for route in primary_routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next", route
        assert "群运营计划" in response.text, route


def test_navigation_definition_matches_screenshot_target():
    assert [(group["title"], [item["label"] for item in group["items"]]) for group in ADMIN_NAV_GROUPS] == checker.TARGET_NAV_GROUPS


def test_checker_returns_ok():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["nav_groups_ready"] is True
    assert result["admin_pages_ready"] is True
    assert result["production_data_ready"] is True
    assert result["fixture_markers"] == []
    assert result["route_404_blockers"] == []


def test_checker_does_not_require_reenabling_disabled_timers():
    result = checker.run_check()

    assert any("timers are intentionally not enabled" in warning for warning in result["warnings"])
    assert result["safe_to_continue_automation_job_recovery"] is True


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-admin-ui-data-parity-test")
    return TestClient(create_app())
