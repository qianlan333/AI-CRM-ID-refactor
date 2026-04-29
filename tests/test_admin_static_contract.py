from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_STATIC = ROOT / "wecom_ability_service" / "static" / "admin_console"
ADMIN_TEMPLATES = ROOT / "wecom_ability_service" / "templates" / "admin_console"


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


def test_customer_profile_uses_admin_api_without_local_request_helper_copy():
    source = _read(ADMIN_STATIC / "customer_profile.js")

    assert "window.AdminApi" in source or "AdminApi" in source
    assert not re.search(r"\bfunction\s+requestJson\s*\(", source)
    assert "fetch(" not in source
    assert "customerPulseAccessHeaders" in source
    assert "requestCustomerPulseJson" in source
    assert "admin_action_token" in source or "adminActionToken" in source
    assert "data-customer-pulse" in source or "customerPulse" in source
    assert "automation" in source


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
