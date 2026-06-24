from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


STATIC_ROOT = Path(__file__).resolve().parents[1] / "aicrm_next" / "frontend_compat" / "static" / "admin_console"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_retired_runtime_v2_package_is_removed() -> None:
    assert not (PROJECT_ROOT / "aicrm_next" / "automation_runtime_v2").exists()


def test_retired_runtime_v2_routes_are_not_registered() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    for path in [
        "/api/automation-runtime/v2/events",
        "/api/automation-runtime/v2/replay",
        "/api/automation-runtime/v2/runtime-check",
    ]:
        response = client.get(path)
        assert response.status_code in {404, 410}
