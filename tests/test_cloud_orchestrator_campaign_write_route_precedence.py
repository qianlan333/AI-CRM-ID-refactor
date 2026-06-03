from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from aicrm_next.cloud_orchestrator.campaigns_write import reset_campaign_write_fixture_state
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


def test_campaign_write_exact_routes_win_over_production_compat_wildcard():
    result = checker.run_check()
    samples = result["resolution_samples"]

    for method, path in [
        ("POST", "/api/admin/cloud-orchestrator/campaigns/batch-start"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/start"),
        ("PATCH", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps/0"),
    ]:
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.cloud_orchestrator.api"

    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "aicrm_next.cloud_orchestrator.api"


def test_campaign_write_requests_do_not_call_legacy_forward(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_campaign_read_fixture_state()
    reset_campaign_write_fixture_state()

    from aicrm_next.production_compat import api as production_api

    calls: list[str] = []

    async def fake_forward(*args, **kwargs):
        calls.append("legacy_forward")
        raise AssertionError("campaign write route should not use production_compat")

    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fake_forward)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve",
        json={},
        headers={"Idempotency-Key": "write-precedence-approve"},
    )
    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json()["source_status"] == "next_command"
    assert calls == []
