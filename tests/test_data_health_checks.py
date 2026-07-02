from __future__ import annotations

import pytest


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_data_health_summary_exposes_registered_checks(client) -> None:
    response = client.get("/api/admin/data-health/summary")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["overall_status"] == "ok"
    check_ids = {item["check_id"] for item in body["checks"]}
    assert {
        "identity_legacy_column_guard",
        "table_lifecycle_manifest_guard",
        "retired_table_runtime_reference_guard",
        "unionid_orphan_fact_guard",
        "identity_resolution_queue_backlog",
        "projection_freshness_customer_read_model",
        "broadcast_job_blocked_backlog",
        "external_effect_failed_retryable_backlog",
        "questionnaire_submission_without_user_guard",
        "payment_order_without_user_guard",
    } <= check_ids
    assert body["counts"]["fail"] == 0
    assert body["counts"]["ok"] >= 3


def test_data_health_checks_do_not_expose_raw_identity_values(client) -> None:
    response = client.get("/api/admin/data-health/checks")

    assert response.status_code == 200
    text = response.text
    for forbidden in ("external_userid_value", "openid_value", "mobile_normalized", "raw_payload_json"):
        assert forbidden not in text


def test_data_health_check_detail_and_missing_check(client) -> None:
    detail = client.get("/api/admin/data-health/checks/table_lifecycle_manifest_guard")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ok"] is True
    assert payload["check"]["check_id"] == "table_lifecycle_manifest_guard"
    assert payload["check"]["status"] == "ok"

    missing = client.get("/api/admin/data-health/checks/not_a_check")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "data_health_check_not_found"
