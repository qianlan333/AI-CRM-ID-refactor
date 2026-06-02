from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_questionnaire_admin_list_page_exposes_next_read_status_without_facade() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    html = response.text
    assert "data-route-owner=\"ai_crm_next\"" in html
    assert "data-source-status=\"local_contract_probe\"" in html
    assert "data-read-model-status=\"fixture\"" in html
    assert "data-fallback-used=\"false\"" in html
    assert "hxc-activation-v1" in html


def test_questionnaire_admin_new_page_is_readonly_shell_without_write_execution() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires/new")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "新建问卷" in response.text
    assert "initialQuestionnaireId: null" in response.text


def test_questionnaire_admin_detail_page_uses_next_read_model_editor_payload() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires/1")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "黄小璨激活问卷" in response.text
    assert "hxc-activation-v1" in response.text
