from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_questionnaire_editor_uses_unified_next_tag_catalog_source() -> None:
    source = (ROOT / "aicrm_next/frontend_compat/templates/admin_questionnaires.html").read_text(encoding="utf-8")

    assert "fetchJson('/api/admin/wecom/tags')" in source
    assert "/api/admin/wecom/tag-groups" not in source
    assert "tag-modal" in source
    assert "availableTagMap" in source


def test_admin_and_sidebar_adjacent_selectors_use_same_tag_catalog_source() -> None:
    files = {
        "tag_management": ROOT / "aicrm_next/frontend_compat/static/admin_console/wecom_tag_management.js",
        "automation_agent": ROOT / "aicrm_next/frontend_compat/static/admin_console/automation_agent_config_tag_picker.js",
        "channel_admission": ROOT / "aicrm_next/frontend_compat/static/admin_console/channel_admission_pages.js",
    }
    sources = {name: path.read_text(encoding="utf-8") for name, path in files.items()}

    assert "/api/admin/wecom/tags" in sources["tag_management"]
    assert "/api/admin/wecom/tag-groups" in sources["tag_management"]
    assert "apiUrls.wecom_tags" in sources["automation_agent"]
    assert "(bootstrap.api_urls || {}).wecom_tags" in sources["channel_admission"]
    assert "/api/admin/wecom/tags" in sources["channel_admission"]


def test_sidebar_signup_tags_status_is_not_a_tag_catalog_selector() -> None:
    inventory = (ROOT / "docs/architecture/wecom_tag_read_route_inventory.md").read_text(encoding="utf-8")

    assert "/api/sidebar/signup-tags/status" in inventory
    assert "No separate sidebar tag catalog selector" in inventory
