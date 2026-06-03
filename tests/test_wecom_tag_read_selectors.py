from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_questionnaire_and_adjacent_selectors_read_unified_tag_catalog_source() -> None:
    questionnaire = Path("aicrm_next/frontend_compat/templates/admin_questionnaires.html").read_text(encoding="utf-8")
    tag_management_template = Path("aicrm_next/frontend_compat/templates/admin_console/config_wecom_tags.html").read_text(encoding="utf-8")
    tag_management = Path("aicrm_next/frontend_compat/static/admin_console/wecom_tag_management.js").read_text(encoding="utf-8")
    automation_picker = Path("aicrm_next/frontend_compat/static/admin_console/automation_agent_config_tag_picker.js").read_text(encoding="utf-8")
    automation_channel_model = Path("aicrm_next/frontend_compat/static/admin_console/automation_agent_config_channel_model.js").read_text(encoding="utf-8")
    channel_pages = Path("aicrm_next/frontend_compat/static/admin_console/channel_admission_pages.js").read_text(encoding="utf-8")
    legacy_routes = Path("aicrm_next/frontend_compat/legacy_routes.py").read_text(encoding="utf-8")

    assert "fetchJson('/api/admin/wecom/tags')" in questionnaire
    assert 'data-api-tags="/api/admin/wecom/tags"' in tag_management_template
    assert 'data-api-groups="/api/admin/wecom/tag-groups"' in tag_management_template
    assert "/api/admin/wecom/tags" in tag_management
    assert "/api/admin/wecom/tag-groups" in tag_management
    assert "apiUrls.wecom_tags" in automation_picker
    assert "AutomationAgentConfig.loadWeComTags" in automation_channel_model
    assert "(bootstrap.api_urls || {}).wecom_tags" in channel_pages
    assert '"wecom_tags": "/api/admin/wecom/tags"' in legacy_routes
    assert "SELECT " not in questionnaire
    assert "SELECT " not in automation_picker
    assert "SELECT " not in channel_pages


def test_questionnaire_tag_selector_treats_degraded_empty_catalog_as_warning() -> None:
    questionnaire = Path("aicrm_next/frontend_compat/templates/admin_questionnaires.html").read_text(encoding="utf-8")

    assert "data.degraded || !state.availableTags.length" in questionnaire
    assert "data.page_error || '当前未获取到企微标签，可手工填写 tag_id'" in questionnaire
    assert "tagCatalogMessageEl.className = 'inline-alert warning'" in questionnaire
    assert "tagCatalogMessageEl.className = 'inline-alert error'" in questionnaire
    assert "extractErrorMessage(data)" in questionnaire


def test_sidebar_signup_tags_status_is_not_a_tag_catalog_selector() -> None:
    inventory = Path("docs/architecture/wecom_tag_read_route_inventory.md").read_text(encoding="utf-8")

    assert "/api/sidebar/signup-tags/status" in inventory
    assert "No separate sidebar tag catalog selector" in inventory


def test_frontend_backend_contract_matrix_documents_real_entry_points() -> None:
    inventory = Path("docs/architecture/wecom_tag_read_route_inventory.md").read_text(encoding="utf-8")

    for marker in [
        "/admin/wecom-tags",
        "/admin/questionnaires/new",
        "/admin/questionnaires/{questionnaire_id}",
        "/admin/channels",
        "/admin/channels/{channel_id}/edit",
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/{program_id}/setup",
        "data-api-tags=\"/api/admin/wecom/tags\"",
        "fetchJson('/api/admin/wecom/tags')",
        "apiUrls.wecom_tags",
        "PostgresTagCatalogRepository",
        "wecom_tags_read_next_native",
        "wecom_tag_groups_read_next_native",
    ]:
        assert marker in inventory


def test_frontend_entry_pages_expose_tag_api_urls_without_legacy_facade(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-frontend-contract")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    wecom_page = client.get("/admin/wecom-tags")
    questionnaire_new = client.get("/admin/questionnaires/new")
    channels_page = client.get("/admin/channels")
    automation_page = client.get("/admin/automation-conversion")

    for response in [wecom_page, questionnaire_new, channels_page, automation_page]:
        assert response.status_code != 500

    assert 'data-api-tags="/api/admin/wecom/tags"' in wecom_page.text
    assert 'data-api-groups="/api/admin/wecom/tag-groups"' in wecom_page.text
    assert "fetchJson('/api/admin/wecom/tags')" in questionnaire_new.text
    assert "/api/admin/channels?limit=300" in channels_page.text
    assert "自动化运营" in automation_page.text


def test_selector_source_route_returns_frontend_compatible_items(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-selector-source")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = TestClient(create_app(), raise_server_exceptions=False).get("/api/admin/wecom/tags")
    payload = response.json()

    assert response.status_code == 200
    assert payload["items"]
    assert {"tag_id", "tag_name", "group_name", "group_id"}.issubset(payload["items"][0])
    assert payload["route_owner"] == "ai_crm_next"
