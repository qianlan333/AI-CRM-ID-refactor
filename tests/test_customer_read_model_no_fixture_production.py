from __future__ import annotations

from aicrm_next.customer_read_model.application import ListCustomersQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest


def test_production_mode_does_not_return_fixture_customer_success(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("CUSTOMER_READ_MODEL_REPO_BACKEND", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is False
    assert payload["source_status"] == "production_unavailable"
    assert payload["read_model_status"] == "unavailable"
    assert payload["customers"] == []
    assert "FixtureCustomerReadRepository" not in str(payload)
    assert "fixture repository" not in str(payload).lower()
    assert "local_contract_probe" not in str(payload)
    assert "张小蓝" not in str(payload)
