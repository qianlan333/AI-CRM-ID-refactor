from __future__ import annotations

from aicrm_next.questionnaire.application import (
    GetQuestionnaireDetailQuery,
    ListQuestionnairesQuery,
    build_questionnaire_share_payload,
)
from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state


def test_next_questionnaire_application_lists_and_reads_fixture_contract():
    reset_questionnaire_fixture_state()

    payload = ListQuestionnairesQuery().execute()
    detail = GetQuestionnaireDetailQuery().execute(1)

    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["questionnaires"][0]["slug"] == "hxc-activation-v1"
    assert detail["ok"] is True
    assert detail["questionnaire"]["slug"] == "hxc-activation-v1"
    assert detail["questions"]


def test_next_questionnaire_share_payload_keeps_public_paths():
    reset_questionnaire_fixture_state()
    questionnaire = GetQuestionnaireDetailQuery().execute(1)["questionnaire"]

    share = build_questionnaire_share_payload(questionnaire, share_url="https://crm.example.test/s/hxc-activation-v1")

    assert share["questionnaire_id"] == 1
    assert share["slug"] == "hxc-activation-v1"
    assert share["public_path"] == "/s/hxc-activation-v1"
    assert share["url"] == "https://crm.example.test/s/hxc-activation-v1"
    assert share["qr_data_url"].startswith("data:image/svg+xml")
