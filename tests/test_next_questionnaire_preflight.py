from __future__ import annotations

from aicrm_next.questionnaire.application import GetQuestionnairePreflightQuery


def test_next_questionnaire_preflight_reads_runtime_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "runtime-secret")
    monkeypatch.setenv("WECHAT_MP_APP_ID", "wx-runtime-app")
    monkeypatch.setenv("WECHAT_MP_APP_SECRET", "wx-runtime-secret")
    monkeypatch.setenv("WECOM_CORP_ID", "ww-runtime")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "contact-runtime-secret")
    monkeypatch.setenv("WECOM_SECRET", "runtime-secret")
    monkeypatch.setenv("WECOM_API_BASE", "https://qyapi.example.test")

    payload = GetQuestionnairePreflightQuery()()

    assert payload["status"] == "ok"
    assert payload["checks"]["wechat_oauth_configured"] is True
    assert payload["checks"]["wecom_contact_configured"] is True
    assert payload["checks"]["wecom_tags_api_available"] is True


def test_next_questionnaire_preflight_forwards_to_legacy_when_production_ready(monkeypatch):
    import pytest

    responses = pytest.importorskip("fastapi.responses")
    testclient = pytest.importorskip("fastapi.testclient")

    from aicrm_next.main import create_app
    import aicrm_next.questionnaire.api as questionnaire_api

    forwarded_paths: list[str] = []

    async def fake_forward_to_legacy_flask(request):
        forwarded_paths.append(request.url.path)
        return responses.JSONResponse(
            {
                "wechat_oauth_configured": True,
                "wecom_contact_configured": True,
                "wecom_tags_api_available": True,
            },
            headers={"X-AICRM-Compatibility-Facade": "legacy_flask_facade"},
        )

    monkeypatch.setenv("SECRET_KEY", "questionnaire-preflight-forwarding-test")
    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    monkeypatch.setattr(questionnaire_api, "forward_to_legacy_flask", fake_forward_to_legacy_flask)

    response = testclient.TestClient(create_app()).get("/api/admin/questionnaires/preflight")

    assert response.status_code == 200
    assert response.headers["x-aicrm-compatibility-facade"] == "legacy_flask_facade"
    assert response.json()["wechat_oauth_configured"] is True
    assert response.json()["wecom_contact_configured"] is True
    assert response.json()["wecom_tags_api_available"] is True
    assert forwarded_paths == ["/api/admin/questionnaires/preflight"]
