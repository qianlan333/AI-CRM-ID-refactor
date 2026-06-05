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


def test_existing_get_export_route_downloads_csv_without_storage_file(client: TestClient) -> None:
    response = client.get("/api/admin/questionnaires/1/export", headers={"Idempotency-Key": "questionnaire-export-get"})

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith('attachment; filename="questionnaire-hxc-activation-v1-submissions.csv"')
    assert response.headers["X-AICRM-Source-Status"] == "next_command"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    csv_text = response.content.decode("utf-8-sig")
    assert "submission_id,submitted_at,external_userid,mobile,matched_by,score,final_tags,answers" in csv_text
    assert "sub_fixture_001" in csv_text
