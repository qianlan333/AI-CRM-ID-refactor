from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


STATIC_ROOT = Path(__file__).resolve().parents[1] / "aicrm_next" / "frontend_compat" / "static" / "admin_console"


def test_retired_automation_overview_static_bundle_is_removed() -> None:
    retired_files = [
        "automation_overview.js",
        "automation_overview_actions.js",
        "automation_overview_core.js",
        "automation_overview_renderers.js",
    ]

    for filename in retired_files:
        assert not (STATIC_ROOT / filename).exists()


def test_retired_customer_profile_automation_actions_static_file_is_removed() -> None:
    assert not (STATIC_ROOT / "customer_profile_automation.js").exists()


def test_retired_automation_overview_api_remains_gone() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/automation-conversion/overview")

    assert response.status_code == 410
    assert response.headers["X-AICRM-Legacy-Automation-Retired"] == "true"
    assert response.json()["error"] == "legacy_automation_overview_retired"
