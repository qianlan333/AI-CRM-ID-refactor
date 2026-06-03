from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_MODE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_cloud_orchestrator_media_upload_returns_legacy_and_next_contract(monkeypatch):
    response = _client(monkeypatch).post(
        "/api/admin/cloud-orchestrator/media/upload",
        headers={"Idempotency-Key": "cloud-media-upload-test-001"},
        files={"image": ("probe.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    payload = response.json()
    assert payload["ok"] is True
    assert payload["media_id"].startswith("fake_media_")
    assert payload["file_name"] == "probe.png"
    assert payload["content_type"] == "image/png"
    assert payload["size"] == len(PNG_BYTES)
    assert payload["command_id"].startswith("cmd_cloud_media_")
    assert payload["source_status"] == "next_cloud_orchestrator_media_upload"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["adapter_mode"] == "real_blocked"
    assert payload["real_external_call_executed"] is False
    assert payload["wecom_media_upload_executed"] is False
    assert payload["side_effect_plan"]["effect_type"] == "wecom.media.upload"
    assert payload["side_effect_plan"]["requires_approval"] is True
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"


def test_cloud_orchestrator_media_upload_fake_mode_returns_usable_media_id(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_MODE", "fake")
    client = _client(monkeypatch)
    monkeypatch.setenv("AICRM_NEXT_CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_MODE", "fake")

    response = client.post(
        "/api/admin/cloud-orchestrator/media/upload",
        files={"image": ("probe.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_mode"] == "fake"
    assert payload["media_id"].startswith("fake_wecom_media_")
    assert payload["adapter_result"]["side_effect_executed"] is False


def test_cloud_orchestrator_media_upload_options_is_next_diagnostics(monkeypatch):
    response = _client(monkeypatch).options("/api/admin/cloud-orchestrator/media/upload")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    payload = response.json()
    assert payload["source_status"] == "next_cloud_orchestrator_media_upload"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["wecom_media_upload_executed"] is False
    assert payload["allowed_methods"] == ["POST", "OPTIONS"]


def test_cloud_orchestrator_media_upload_missing_image_is_controlled_400(monkeypatch):
    response = _client(monkeypatch).post("/api/admin/cloud-orchestrator/media/upload")

    assert response.status_code == 400
    assert response.json()["error"] == "missing_image"
    assert response.json()["fallback_used"] is False


def test_cloud_orchestrator_media_upload_invalid_content_type_is_controlled_400(monkeypatch):
    response = _client(monkeypatch).post(
        "/api/admin/cloud-orchestrator/media/upload",
        files={"image": ("note.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_content_type"


def test_cloud_orchestrator_media_upload_empty_file_is_controlled_400(monkeypatch):
    response = _client(monkeypatch).post(
        "/api/admin/cloud-orchestrator/media/upload",
        files={"image": ("empty.png", b"", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "empty_image"
