from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "aicrm_next" / "frontend_compat"
STATIC = FRONTEND / "static" / "admin_console"
TEMPLATES = FRONTEND / "templates" / "admin_console"
OPERATION_PANEL = TEMPLATES / "_automation_operation_orchestration_panel.html"
HXC_TEMPLATE = TEMPLATES / "hxc_dashboard.html"
CAMPAIGN_TEMPLATE = TEMPLATES / "cloud_campaigns_workspace.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_next_automation_operation_panel_has_no_private_asset_binding() -> None:
    source = _read(OPERATION_PANEL)

    for forbidden in [
        "请输入图片" + "素材编号",
        "请输入小程序" + "素材编号",
        "请输入附件" + "素材编号",
        "data-bind" + "-asset",
    ]:
        assert forbidden not in source
    assert "AICRMSendContentComposer.open" in source


def test_next_hxc_migrated_template_has_no_private_material_grid() -> None:
    source = _read(HXC_TEMPLATE)

    assert "AICRMSendContentComposer.open" in source
    for forbidden in [
        "hxc-" + "img-grid",
        "hxc-" + "mp-grid",
        "hxc-" + "asset-card",
        "hxc-" + "broadcast-modal",
        "load" + "Assets",
        "render" + "ImageGrid",
        "render" + "MpGrid",
    ]:
        assert forbidden not in source


def test_next_campaign_cleanup_guard_only_applies_after_migration() -> None:
    source = _read(CAMPAIGN_TEMPLATE)

    if "AICRMSendContentComposer.open" not in source:
        return
    assert "attach" + "MiniprogramPicker" not in source
    assert "mount" + "ImagePicker" not in source
    assert "请输入附件" + "素材编号" not in source


def test_standard_send_content_components_still_exist() -> None:
    composer = _read(STATIC / "send_content_composer.js")
    picker = _read(STATIC / "material_picker.js")

    assert "window.AICRMSendContentComposer" in composer
    assert "AICRMSendContentComposer" in composer
    assert "window.AICRMMaterialPicker" in picker
    assert "AICRMMaterialPicker" in picker


def test_migrated_business_pages_do_not_direct_fetch_material_libraries() -> None:
    migrated_pages = [
        OPERATION_PANEL,
        HXC_TEMPLATE,
        CAMPAIGN_TEMPLATE,
    ]
    direct_fetch_markers = [
        "/api/admin/image-library",
        "/api/admin/miniprogram-library",
        "/api/admin/attachment-library",
    ]

    for path in migrated_pages:
        source = _read(path)
        assert "AICRMSendContentComposer.open" in source
        for marker in direct_fetch_markers:
            assert marker not in source
