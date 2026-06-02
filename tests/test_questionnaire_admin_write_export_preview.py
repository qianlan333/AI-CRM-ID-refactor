from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


def test_questionnaire_export_preview_returns_masked_sample_and_plan_only(client: TestClient) -> None:
    response = client.post(
        "/api/admin/questionnaires/1/export/preview",
        json={"fields": ["external_userid", "answers", "created_at"]},
        headers={"Idempotency-Key": "questionnaire-export-preview"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["command_name"] == "questionnaire.admin.export_preview"
    assert body["source_status"] == "next_command"
    assert body["write_model_status"] == "export_preview_planned"
    assert body["real_external_call_executed"] is False
    assert body["export_preview"]["file_created"] is False
    assert body["export_preview"]["estimated_count"] >= 1
    assert body["export_preview"]["masked_sample"][0]["external_userid"] == "masked"
    assert body["side_effect_plan"]["effect_type"] == "questionnaire.export.preview"
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"


def test_existing_get_export_route_is_audit_command_not_file_download(client: TestClient) -> None:
    response = client.get("/api/admin/questionnaires/1/export", headers={"Idempotency-Key": "questionnaire-export-get"})

    assert response.status_code == 200
    assert "Content-Disposition" not in response.headers
    body = response.json()
    assert body["command_name"] == "questionnaire.admin.export_audit"
    assert body["source_status"] == "next_command"
    assert body["export_preview"]["file_created"] is False
    assert body["real_external_call_executed"] is False
