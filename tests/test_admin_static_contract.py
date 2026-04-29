from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_STATIC = ROOT / "wecom_ability_service" / "static" / "admin_console"
ADMIN_TEMPLATES = ROOT / "wecom_ability_service" / "templates" / "admin_console"

CUSTOMER_PROFILE_MODULES = [
    "customer_profile_core.js",
    "customer_profile_sections.js",
    "customer_profile_pulse.js",
    "customer_profile_followup.js",
    "customer_profile_automation.js",
    "customer_profile.js",
]

CUSTOMER_PULSE_INBOX_MODULES = [
    "customer_pulse_inbox_core.js",
    "customer_pulse_inbox_renderers.js",
    "customer_pulse_inbox_actions.js",
    "customer_pulse_inbox_boot.js",
    "customer_pulse_inbox.js",
]

AUTOMATION_AUTO_REPLY_MODULES = [
    "automation_auto_reply_core.js",
    "automation_auto_reply_outputs.js",
    "automation_auto_reply_modal.js",
    "automation_auto_reply_actions.js",
    "automation_auto_reply.js",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_base_template_loads_admin_api_client_before_page_scripts():
    source = _read(ADMIN_TEMPLATES / "base.html")

    admin_api_client_index = source.index("admin_console/admin_api_client.js")
    admin_console_index = source.index("admin_console/admin_console.js")
    scripts_extra_index = source.index("{% block scripts_extra %}")
    body_close_index = source.index("</body>")

    assert admin_api_client_index < admin_console_index
    assert admin_console_index < scripts_extra_index
    assert scripts_extra_index < body_close_index


def test_admin_api_client_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "admin_api_client.js")

    assert "window.AdminApi" in source
    assert "safeJsonParse" in source
    assert "escapeHtml" in source
    assert "requestJson" in source
    assert "isPermissionError" in source
    assert "normalizeRequestError" in source
    assert "credentials" in source
    assert "same-origin" in source
    assert "FormData" in source
    assert "URLSearchParams" in source
    assert "JSON.stringify" in source
    assert "response.text()" in source
    assert re.search(r"error\.status\s*=", source)
    assert re.search(r"error\.payload\s*=", source)
    assert re.search(r"error\.response\s*=", source)
    assert re.search(r"error\.url\s*=", source)
    assert re.search(r"error\.method\s*=", source)


def test_customer_detail_loads_customer_profile_modules_in_order():
    source = _read(ADMIN_TEMPLATES / "customer_detail.html")

    positions = [source.index(f"admin_console/{filename}") for filename in CUSTOMER_PROFILE_MODULES]

    assert positions == sorted(positions)
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])


def test_customer_profile_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in CUSTOMER_PROFILE_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.CustomerProfile" in source or "CustomerProfile" in source
        for token in forbidden_tokens:
            assert token not in source


def test_customer_profile_entrypoint_only_bootstraps_modules():
    source = _read(ADMIN_STATIC / "customer_profile.js")

    assert "DOMContentLoaded" in source
    assert "bootBasicSections" in source
    assert "bootCustomerPulse" in source
    assert "bootFollowupOrchestrator" in source
    assert "bootAutomation" in source
    assert not re.search(r"\bfunction\s+requestJson\s*\(", source)
    assert "fetch(" not in source
    assert "function renderCustomerPulse" not in source
    assert "function renderMessages" not in source
    assert "function executeAutomationAction" not in source


def test_customer_profile_core_exposes_shared_profile_contract():
    source = _read(ADMIN_STATIC / "customer_profile_core.js")

    assert "customerPulseAccessHeaders" in source
    assert "requestCustomerPulseJson" in source
    assert "showSectionError" in source
    assert "showSectionEmpty" in source
    assert "state" in source


def test_customer_profile_pulse_module_keeps_action_contract():
    source = _read(ADMIN_STATIC / "customer_profile_pulse.js")

    assert "loadCustomerPulse" in source
    assert "executeCustomerPulseAction" in source
    assert "submitCustomerPulseFeedback" in source
    assert "loadCustomerPulsePreview" in source
    assert "loadCustomerPulseEvidence" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_customer_profile_automation_module_keeps_action_contract():
    source = _read(ADMIN_STATIC / "customer_profile_automation.js")

    assert "loadAutomationMember" in source
    assert "executeAutomationAction" in source
    assert "data-automation-action" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_customer_profile_sections_module_keeps_basic_renderers():
    source = _read(ADMIN_STATIC / "customer_profile_sections.js")

    assert "renderLiveTags" in source
    assert "renderQuestionnaireAnswers" in source
    assert "renderMessages" in source


def test_customer_profile_followup_module_keeps_widget_contract():
    source = _read(ADMIN_STATIC / "customer_profile_followup.js")

    assert "renderFollowupOrchestratorWidget" in source
    assert "loadFollowupOrchestrator" in source


def test_customer_pulse_inbox_uses_admin_api_without_local_request_helper_copy():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox.js")

    assert "DOMContentLoaded" in source
    assert "CustomerPulseInbox.boot" in source
    assert not re.search(r"\bfunction\s+requestJson\s*\(", source)
    assert "fetch(" not in source
    assert "function renderDetail" not in source
    assert "function loadPreview" not in source
    assert "function submitAction" not in source


def test_customer_pulse_inbox_loads_modules_in_order():
    source = _read(ADMIN_TEMPLATES / "customer_pulse_inbox.html")

    positions = [source.index(f"admin_console/{filename}") for filename in CUSTOMER_PULSE_INBOX_MODULES]

    assert positions == sorted(positions)
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])
    for filename in CUSTOMER_PULSE_INBOX_MODULES:
        script_start = source.rfind("<script", 0, source.index(f"admin_console/{filename}"))
        script_end = source.index("</script>", source.index(f"admin_console/{filename}"))
        script_tag = source[script_start:script_end]
        assert "defer" in script_tag


def test_customer_pulse_inbox_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in CUSTOMER_PULSE_INBOX_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.CustomerPulseInbox" in source or "CustomerPulseInbox" in source
        for token in forbidden_tokens:
            assert token not in source


def test_customer_pulse_inbox_core_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_core.js")

    assert "store" in source
    assert "cardApiUrl" in source
    assert "customerPulseAccessHeaders" in source
    assert "setDetailState" in source
    assert "inlineStateHtml" in source


def test_customer_pulse_inbox_renderers_keep_detail_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_renderers.js")

    assert "renderDetail" in source
    assert "renderSelectedCard" in source
    assert "evidenceRefsHtml" in source
    assert "actionSlotHtml" in source
    assert "pulseFormFields" in source


def test_customer_pulse_inbox_actions_keep_api_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_actions.js")

    assert "ensureCardDetail" in source
    assert "loadCardDetail" in source
    assert "loadPreview" in source
    assert "loadEvidence" in source
    assert "submitAction" in source
    assert "submitFeedback" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_customer_pulse_inbox_boot_keeps_interaction_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_boot.js")

    assert "wireInboxInteractions" in source or "wireInteractions" in source
    assert "data-card-select" in source
    assert "data-detail-action-form" in source
    assert "data-customer-pulse-inbox-json" in source
    assert "boot" in source


def test_automation_auto_reply_template_loads_modules_in_order_and_removes_inline_logic():
    source = _read(ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html")

    positions = [source.index(f"admin_console/{filename}") for filename in AUTOMATION_AUTO_REPLY_MODULES]

    assert positions == sorted(positions)
    assert "{{ super() }}" in source
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])
    for filename in AUTOMATION_AUTO_REPLY_MODULES:
        script_start = source.rfind("<script", 0, source.index(f"admin_console/{filename}"))
        script_end = source.index("</script>", source.index(f"admin_console/{filename}"))
        script_tag = source[script_start:script_end]
        assert "defer" in script_tag

    assert 'id="automation-auto-reply-root"' in source
    assert "data-api-urls" in source
    assert "data-admin-action-token" in source
    assert "function requestJson" not in source
    assert "function renderOutputs" not in source
    assert "function runAction" not in source
    assert "data-reply-action-url" in source
    assert "reply-output-modal" in source


def test_automation_auto_reply_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in AUTOMATION_AUTO_REPLY_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.AutomationAutoReply" in source or "AutomationAutoReply" in source
        for token in forbidden_tokens:
            assert token not in source


def test_automation_auto_reply_core_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_core.js")

    assert "getAdminActionToken" in source
    assert "getApiUrls" in source
    assert "withOutputId" in source
    assert "withWebhookOutputId" in source
    assert "withWecomOutputId" in source
    assert "copyClipboardText" in source
    assert "state" in source


def test_automation_auto_reply_outputs_keeps_review_output_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_outputs.js")

    assert "renderOutputs" in source
    assert "loadOutputs" in source
    assert "data-review-action" in source
    assert "webhook" in source
    assert "wecom_send" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_automation_auto_reply_modal_keeps_rejected_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_modal.js")

    assert "openRejectModal" in source
    assert "closeRejectModal" in source
    assert "setModalFeedback" in source
    assert "review_note" in source
    assert "decision" in source
    assert "rejected" in source


def test_automation_auto_reply_actions_keep_formdata_action_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_actions.js")

    assert "runAction" in source
    assert "data-reply-action-url" in source
    assert "data-reply-toggle-enabled" in source
    assert "FormData" in source
    assert "admin_action_token" in source
    assert "X-Requested-With" in source


def test_automation_auto_reply_entrypoint_only_bootstraps_modules():
    source = _read(ADMIN_STATIC / "automation_auto_reply.js")

    assert "DOMContentLoaded" in source
    assert "boot" in source
    assert "function renderOutputs" not in source
    assert "function runAction" not in source
    assert "function requestJson" not in source


def test_no_frontend_build_tooling_was_added():
    forbidden_paths = [
        ROOT / "package.json",
        ROOT / "vite.config.ts",
        ROOT / "tsconfig.json",
        ROOT / "node_modules",
        ROOT / "web" / "package.json",
    ]

    assert not [path for path in forbidden_paths if path.exists()]
