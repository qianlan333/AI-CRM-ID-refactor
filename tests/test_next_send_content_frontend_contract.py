from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aicrm_next" / "frontend_compat" / "static" / "admin_console"
TEMPLATE = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console" / "_automation_operation_orchestration_panel.html"
HXC_TEMPLATE = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console" / "hxc_dashboard.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_send_content_composer_exists_and_exposes_global_api() -> None:
    source = _read(STATIC / "send_content_composer.js")

    assert "window.AICRMSendContentComposer" in source
    assert ".open" in source or "{ open }" in source


def test_material_picker_exists_and_exposes_global_api() -> None:
    source = _read(STATIC / "material_picker.js")

    assert "window.AICRMMaterialPicker" in source
    assert ".open" in source or "{ open }" in source


def test_send_content_composer_excludes_non_standard_controls() -> None:
    source = _read(STATIC / "send_content_composer.js")

    for forbidden in ["插入班期", "插入顾问名", "AI 改写", "保存为话术模板"]:
        assert forbidden not in source


def test_send_content_composer_supports_text_disabled_agent_mode() -> None:
    source = _read(STATIC / "send_content_composer.js")

    assert "textEnabled" in source
    assert "textEnabled=false" not in source
    assert "Agent 将为每个客户生成个性化话术" in source
    assert 'content_text: textEnabled ? normalized.content_text : ""' in source


def test_operation_panel_references_send_content_composer_assets() -> None:
    source = _read(TEMPLATE)

    assert "send_content_composer.js" in source
    assert "send_content_composer.css" in source
    assert "material_picker.js" in source
    assert "material_picker.css" in source


def test_operation_panel_does_not_prompt_for_material_ids() -> None:
    source = _read(TEMPLATE)

    assert "请输入图片" + "素材编号" not in source
    assert "请输入小程序" + "素材编号" not in source
    assert "请输入附件" + "素材编号" not in source


def test_operation_panel_contains_profile_template_selector_logic() -> None:
    source = _read(TEMPLATE)

    assert "profile-segment-templates/options" in source
    assert "data-profile-template-select" in source
    assert "profile_segment_template_id" in source
    assert "当前画像模板还没有可填写的分层" in source


def test_operation_panel_contains_behavior_rule_logic() -> None:
    source = _read(TEMPLATE)

    assert "behavior-segment-rules" in source
    assert "data-behavior-rule-select" in source
    assert "lt_2" in source
    assert "between_2_9" in source
    assert "gte_10" in source


def test_operation_panel_contains_agent_selector_logic() -> None:
    source = _read(TEMPLATE)

    assert "/api/admin/automation-conversion/agents" in source
    assert "data-agent-select" in source
    assert "textEnabled: false" in source
    assert "agent-materials" in source


def test_material_selection_only_uses_material_picker_contract() -> None:
    panel = _read(TEMPLATE)
    composer = _read(STATIC / "send_content_composer.js")
    picker = _read(STATIC / "material_picker.js")

    assert "AICRMMaterialPicker.open" in composer
    assert "/api/admin/material-picker/items" in picker
    for source in [panel, composer, picker]:
        assert "/api/admin/image-library" not in source
        assert "/api/admin/miniprogram-library" not in source
        assert "/api/admin/attachment-library" not in source
        assert "hxc-" + "asset-grid" not in source
        assert "hxc-" + "img-grid" not in source
        assert "hxc-" + "mp-grid" not in source


def test_hxc_dashboard_uses_standard_composer_without_legacy_broadcast() -> None:
    source = _read(HXC_TEMPLATE)

    assert "AICRMSendContentComposer.open" in source
    assert "send_content_composer.js" in source
    assert "/api/admin/hxc-dashboard/broadcast-tasks" in source
    assert not re.search(r"fetch\([\"']/api/admin/hxc-dashboard/broadcast[\"']", source)
    assert "/api/admin/image-library" not in source
    assert "/api/admin/miniprogram-library" not in source
    assert "hxc-" + "asset-grid" not in source
    assert "hxc-" + "img-grid" not in source
    assert "hxc-" + "mp-grid" not in source
