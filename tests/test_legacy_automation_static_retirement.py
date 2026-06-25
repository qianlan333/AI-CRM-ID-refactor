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


def test_retired_automation_overview_api_is_removed() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/automation-conversion/overview")

    assert response.status_code == 404


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


def test_retired_runtime_v2_realtest_guard_is_removed_from_broadcast_worker() -> None:
    source = (PROJECT_ROOT / "aicrm_next" / "background_jobs" / "broadcast_queue_worker.py").read_text(encoding="utf-8")

    assert "RuntimeV2真实链路测试" not in source
    assert "runtime_v2_realtest_" not in source
    assert "realtest_sender_not_allowed" not in source
    assert "realtest_target_not_allowed" not in source
