from __future__ import annotations

from urllib.parse import unquote

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-questionnaire-share-test")
    return TestClient(create_app())


def test_questionnaire_share_endpoint_returns_public_link_and_qr(monkeypatch):
    response = _client(monkeypatch).get("/api/admin/questionnaires/1/share")

    assert response.status_code == 200
    share = response.json()["share"]
    assert share["questionnaire_id"] == 1
    assert share["slug"] == "hxc-activation-v1"
    assert share["url"] == "http://testserver/s/hxc-activation-v1"
    assert share["qr_data_url"].startswith("data:image/svg+xml;charset=UTF-8,")
    assert 'xmlns="http://www.w3.org/2000/svg"' in unquote(share["qr_data_url"])


def test_questionnaire_share_endpoint_uses_production_public_path(monkeypatch):
    import aicrm_next.questionnaire.api as questionnaire_api

    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        questionnaire_api,
        "get_questionnaire_detail_from_legacy",
        lambda questionnaire_id: {
            "ok": True,
            "questionnaire": {
                "id": questionnaire_id,
                "slug": "real-questionnaire",
                "title": "真实生产问卷",
                "name": "真实生产问卷",
                "enabled": True,
                "is_disabled": False,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-05-22T00:00:00Z",
                "submission_count": 1171,
                "assessment_enabled": False,
                "public_path": "/s/real-questionnaire",
            },
        },
    )

    response = _client(monkeypatch).get("/api/admin/questionnaires/101/share")

    assert response.status_code == 200
    share = response.json()["share"]
    assert share["questionnaire_id"] == 101
    assert share["title"] == "真实生产问卷"
    assert share["url"] == "http://testserver/s/real-questionnaire"
    assert share["qr_data_url"].startswith("data:image/svg+xml;charset=UTF-8,")


def test_questionnaire_admin_page_renders_share_modal(monkeypatch):
    response = _client(monkeypatch).get("/admin/questionnaires")

    assert response.status_code == 200
    html = response.text
    assert 'id="questionnaire-share-modal"' in html
    assert "问卷链接" in html
    assert "问卷二维码" in html
    assert "保存二维码" in html
    assert "/api/admin/questionnaires/${item.id}/share" in html
