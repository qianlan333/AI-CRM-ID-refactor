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

    assert "window.AdminApi" in source or "AdminApi" in source
    assert not re.search(r"\bfunction\s+requestJson\s*\(", source)
    assert "fetch(" not in source
    assert "customerPulseAccessHeaders" in source
    assert "pulseInboxStore" in source
    assert "cardApiUrl" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_no_frontend_build_tooling_was_added():
    forbidden_paths = [
        ROOT / "package.json",
        ROOT / "vite.config.ts",
        ROOT / "tsconfig.json",
        ROOT / "node_modules",
        ROOT / "web" / "package.json",
    ]

    assert not [path for path in forbidden_paths if path.exists()]
