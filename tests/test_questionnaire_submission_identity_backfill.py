from __future__ import annotations

from aicrm_next.questionnaire.application import ListQuestionnaireSubmissionsQuery
from aicrm_next.questionnaire.h5_write import QuestionnaireH5SubmitCommand, execute_questionnaire_h5_submit
from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state


def test_questionnaire_submission_identity_is_written_by_next_submit_command():
    reset_questionnaire_fixture_state()

    result = execute_questionnaire_h5_submit(
        QuestionnaireH5SubmitCommand(
            questionnaire_slug="hxc-activation-v1",
            answers={"q_activation": "activated"},
            identity={"mobile": "13800138000", "external_userid": "wx_ext_001", "person_id": "person_001"},
            source={"source": "identity-backfill-test"},
            source_route="/s/hxc-activation-v1",
            idempotency_key="identity-backfill-next",
        )
    )

    assert result["ok"] is True
    submissions = ListQuestionnaireSubmissionsQuery().execute(1, limit=10)
    created = [item for item in submissions["submissions"] if item["submission_id"] == result["submission_id"]][0]
    assert created["external_userid"] == "wx_ext_001"
    assert created["mobile"] == "13800138000"
    assert created["person_id"] == "person_001"
