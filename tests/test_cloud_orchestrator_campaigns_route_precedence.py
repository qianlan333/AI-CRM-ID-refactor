from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def _owner_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["route_owner"])
    raise AssertionError(f"missing sample {method} {path}")


def _endpoint_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["endpoint_module"])
    raise AssertionError(f"missing sample {method} {path}")


def test_campaign_read_exact_routes_win_over_production_compat():
    result = checker.run_check()
    samples = result["resolution_samples"]

    paths = [
        "/api/admin/cloud-orchestrator/campaigns",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps",
    ]
    for path in paths:
        assert _owner_for(samples, "GET", path) == "next"
        assert _endpoint_for(samples, "GET", path) == "aicrm_next.cloud_orchestrator.api"

    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "production_compat"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "production_compat"


def test_campaign_read_requests_do_not_touch_legacy_forward(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_campaign_read_fixture_state()

    from aicrm_next.production_compat import api as production_api

    calls: list[str] = []

    async def fake_forward(*args, **kwargs):
        calls.append("legacy_forward")
        raise AssertionError("Next campaign read should not forward to legacy")

    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fake_forward)
    client = TestClient(create_app(), raise_server_exceptions=False)

    for path in [
        "/api/admin/cloud-orchestrator/campaigns",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"

    assert calls == []
