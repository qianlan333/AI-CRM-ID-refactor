from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CHANNEL_FORM = ROOT / "aicrm_next/automation_engine/templates/admin_console/channel_code_form.html"
CHANNEL_JS = ROOT / "aicrm_next/automation_engine/static/admin_console/channel_admission_pages.js"
CHANNEL_CSS = ROOT / "aicrm_next/automation_engine/static/admin_console/channel_admission_pages.css"
PICKER_JS = ROOT / "aicrm_next/frontend_compat/static/admin_console/operation_member_picker.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_channel_form_contains_multi_staff_assignment_without_demo_forbidden_surfaces() -> None:
    html = _read(CHANNEL_FORM)
    js = _read(CHANNEL_JS)
    css = _read(CHANNEL_CSS)
    combined = html + "\n" + js + "\n" + css

    assert "企微客服分配" in html
    assert "按比例分配" in html
    assert "满额切换" in html
    assert "平均比例" not in combined
    assert "权重" not in combined
    assert "扫码模拟" not in combined
    assert "二维码模拟" not in combined
    assert "分配日志模拟" not in combined
    assert "Payload JSON" not in combined
    assert "payload JSON" not in combined
    assert "channel-json-preview" not in combined
    assert "客服人数统计" not in combined
    assert "24h 扫码统计" not in combined
    assert "当前策略统计" not in combined


def test_assignment_strategy_radios_are_before_titles_and_only_two_modes() -> None:
    html = _read(CHANNEL_FORM)

    ratio_block = re.search(r'<label class="strategy-card" data-strategy-card="ratio">(.*?)</label>', html, re.S)
    cap_block = re.search(r'<label class="strategy-card" data-strategy-card="cap_switch">(.*?)</label>', html, re.S)
    assert ratio_block
    assert cap_block
    assert ratio_block.group(1).index('type="radio"') < ratio_block.group(1).index("<strong>按比例分配</strong>")
    assert cap_block.group(1).index('type="radio"') < cap_block.group(1).index("<strong>满额切换</strong>")
    assert html.count('data-assignment-strategy') == 2
    assert 'value="ratio"' in html
    assert 'value="cap_switch"' in html
    assert "weighted_random" not in html
    assert "balanced" not in html
    assert "average_ratio" not in html


def test_channel_form_uses_demo_shell_dom_and_prefixed_css() -> None:
    html = _read(CHANNEL_FORM)
    js = _read(CHANNEL_JS)
    css = _read(CHANNEL_CSS)

    for class_name in [
        "channel-form-v3",
        "breadcrumbs",
        "page-head",
        "card",
        "card-head",
        "card-body",
        "section",
        "section-head",
        "field-grid",
        "strategy-grid",
        "strategy-card",
        "strategy-title",
        "assignee-panel",
        "assignee-toolbar",
        "assignee-list",
        "validation",
        "summary-box",
        "summary-row",
    ]:
        assert class_name in html or class_name in js

    for selector in [
        ".channel-form-v3 .card",
        ".channel-form-v3 .strategy-card",
        ".channel-form-v3 .assignee-panel",
        ".channel-form-v3 .summary-box",
        ".channel-form-v3 .validation",
    ]:
        assert selector in css

    assert "assignee-row" in js
    assert "assignee-name" in js
    assert "assignee-row-actions" in js
    assert "channel-strategy-card" not in html
    assert "channel-assignee-panel" not in html
    assert "channel-selector-box" not in html


def test_channel_type_visibility_and_payload_fields_follow_demo_contract() -> None:
    html = _read(CHANNEL_FORM)
    js = _read(CHANNEL_JS)

    assert "普通二维码" in html
    assert "渠道获客链接" in html
    assert "<span>渠道参数</span>" in html
    assert "<span>原始链接</span>" in html
    assert "<span>最终分享链接</span>" in html
    assert "[data-link-field], [data-link-section]" in js
    assert "node.hidden = !isLink" in js
    assert "[data-qrcode-field], [data-qrcode-section]" in js
    assert "node.hidden = isLink" in js
    assert "auto_accept_friend:" in js
    assert "payload.customer_channel" in js
    assert "link_url:" in js
    assert "final_url:" in js


def test_assignment_rows_show_only_ratio_or_cap_fields_and_validate_before_save() -> None:
    js = _read(CHANNEL_JS)

    assert "分配比例" in js
    assert "24h 上限人数" in js
    assert "ratio_percent: assignmentState.strategy === \"ratio\"" in js
    assert "max_scans_24h: assignmentState.strategy === \"cap_switch\"" in js
    assert "ratio_percent: assignmentState.strategy === \"cap_switch\"" not in js
    assert "max_scans_24h: assignmentState.strategy === \"ratio\"" not in js
    assert "比例合计必须等于 100%" in js
    assert "button.disabled = assignmentState.errors.length > 0" in js
    assert "throw new Error(errors[0])" in js
    assert "weight" not in js.lower()
    assert "weighted_random" not in js
    assert "balanced" not in js
    assert "average_ratio" not in js


def test_add_assignee_uses_operation_member_picker_multiple_mode_without_fake_staff() -> None:
    js = _read(CHANNEL_JS)
    picker = _read(PICKER_JS)

    assert "OperationMemberPicker.open" in js
    assert "multiple: true" in js
    assert "max: Math.max(1, 5 - current.length)" in js
    assert "selectedMembers: []" in js
    assert "disabledUserIds: current.map((item) => item.staff_id)" in js
    assert 'scope: "channel_code"' in js
    assert "page_size: 100" in js
    assert "staffPool" not in js
    assert "Support05" not in js
    assert "selectedMembers" in picker
    assert "disabledUserIds" in picker
    assert "member-modal" in picker
    assert "member-modal__panel" in picker
    assert "member-row" in picker
    assert 'type="checkbox"' in picker


def test_standard_welcome_tag_components_and_hidden_payload_inputs_are_kept() -> None:
    html = _read(CHANNEL_FORM)
    js = _read(CHANNEL_JS)

    assert "AICRMSendContentComposer.open" in js
    assert "AICRMWeComTagPicker.open" in js
    assert "prompt(" not in js
    assert "summary-box" in html
    assert "summary-row" in html
    assert "data-welcome-material-summary" in html
    assert 'name="welcome_message"' in html
    assert 'name="welcome_image_library_ids"' in html
    assert 'name="welcome_miniprogram_library_ids"' in html
    assert 'name="welcome_attachment_library_ids"' in html
    assert 'name="entry_tag_id"' in html
    assert 'name="entry_tag_name"' in html
    assert 'name="entry_tag_group_name"' in html
    assert "welcome_message:" in js
    assert "welcome_image_library_ids:" in js
    assert "welcome_miniprogram_library_ids:" in js
    assert "welcome_attachment_library_ids:" in js
    assert "entry_tag_id:" in js
