from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def test_cloud_orchestrator_media_upload_resolves_to_next_before_production_compat(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    result = checker.run_check()
    sample = next(
        item
        for item in result["resolution_samples"]
        if item["method"] == "POST" and item["path"] == "/api/admin/cloud-orchestrator/media/upload"
    )

    assert sample["route_owner"] == "next"
    assert sample["endpoint_module"] == "aicrm_next.cloud_orchestrator.api"


def test_cloud_orchestrator_media_upload_does_not_call_legacy_forward(monkeypatch):
    import aicrm_next.production_compat.api as production_api

    async def fail_if_called(_request):
        raise AssertionError("legacy forward should not handle cloud media upload")

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fail_if_called)

    response = TestClient(create_app(), raise_server_exceptions=False).options(
        "/api/admin/cloud-orchestrator/media/upload"
    )

    assert response.status_code == 200
    assert response.json()["source_status"] == "next_cloud_orchestrator_media_upload"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
