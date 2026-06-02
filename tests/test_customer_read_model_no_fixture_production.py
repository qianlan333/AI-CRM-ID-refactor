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


def test_production_repo_uses_runtime_database_url(monkeypatch):
    from aicrm_next.customer_read_model import repo as repo_module

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgres://prod_user:prod_pass@db.internal:5432/prod_crm")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("CUSTOMER_READ_MODEL_REPO_BACKEND", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    created_urls: list[str] = []
    dummy_engine = object()
    dummy_session = object()

    def fake_create_engine(url: str, *, future: bool):
        created_urls.append(url)
        assert future is True
        return dummy_engine

    def fake_sessionmaker(*, bind, future: bool):
        assert bind is dummy_engine
        assert future is True
        return lambda: dummy_session

    monkeypatch.setattr(repo_module, "create_engine", fake_create_engine)
    monkeypatch.setattr(repo_module, "sessionmaker", fake_sessionmaker)

    repository = repo_module.build_customer_read_model_repository()

    assert repository.__class__.__name__ == "SqlAlchemyCustomerReadModelRepository"
    assert created_urls == ["postgresql+psycopg://prod_user:prod_pass@db.internal:5432/prod_crm"]
