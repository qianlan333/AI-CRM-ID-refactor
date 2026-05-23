from __future__ import annotations

import sys
import types
from pathlib import Path


def test_questionnaire_external_push_application_contract_is_importable():
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

    from wecom_ability_service.application.questionnaire.commands import (
        RetryQuestionnaireExternalPushCommand,
    )
    from wecom_ability_service.application.questionnaire.queries import (
        GetGlobalQuestionnaireExternalPushLogsQuery,
        GetQuestionnaireExternalPushLogsQuery,
    )

    assert GetQuestionnaireExternalPushLogsQuery
    assert GetGlobalQuestionnaireExternalPushLogsQuery
    assert RetryQuestionnaireExternalPushCommand


def test_admin_questionnaire_console_uses_formal_application_external_push_owner():
    source = (
        Path(__file__).resolve().parents[1]
        / "wecom_ability_service"
        / "http"
        / "admin_questionnaire_push_logs.py"
    ).read_text(encoding="utf-8")

    required_fragments = [
        "GetQuestionnaireExternalPushLogsQuery",
        "GetGlobalQuestionnaireExternalPushLogsQuery",
        "RetryQuestionnaireExternalPushCommand",
    ]
    for fragment in required_fragments:
        assert fragment in source

    forbidden_fragments = [
        "build_questionnaire_external_push_logs_payload",
        "build_global_questionnaire_external_push_logs_payload",
        "retry_questionnaire_external_push_log_for_console",
        "retry_questionnaire_external_push_logs_for_console",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_external_push_pages_do_not_link_via_retired_flask_questionnaire_get_endpoints():
    root = Path(__file__).resolve().parents[1]
    sources = [
        root / "wecom_ability_service" / "http" / "admin_questionnaire_push_logs.py",
        root / "wecom_ability_service" / "application" / "questionnaire" / "queries.py",
        root / "wecom_ability_service" / "templates" / "admin_console" / "questionnaire_external_push_logs.html",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    assert 'url_for("api.admin_console_questionnaires")' not in combined
    assert "url_for('api.admin_console_questionnaires')" not in combined
    assert 'url_for("api.admin_console_questionnaire_detail"' not in combined
    assert "url_for('api.admin_console_questionnaire_detail'" not in combined
    assert "/admin/questionnaires" in combined


def test_global_external_push_payload_builds_next_questionnaire_paths_without_flask_url_for(monkeypatch):
    from wecom_ability_service.application.questionnaire import queries

    row = {
        "id": 1,
        "questionnaire_id": 21,
        "questionnaire_title_snapshot": "真实生产问卷",
        "submission_record_id": 101,
        "retry_from_log_id": None,
        "retry_attempt": 0,
        "user_id": "user-1",
        "target_url": "https://hooks.example.com/apply",
        "request_payload": {},
        "response_status_code": 500,
        "response_body": "HTTP 500",
        "status": "failed",
        "failure_reason": "HTTP 500",
        "created_at": "2026-05-23 11:49:47",
        "updated_at": "2026-05-23 11:49:47",
        "is_retry": False,
        "retry_count": 0,
        "retries": [],
        "latest_log": {"id": 1, "status": "failed"},
        "latest_status": "failed",
        "latest_updated_at": "2026-05-23 11:49:47",
        "has_retry": False,
        "can_retry": True,
    }

    monkeypatch.setattr(
        queries.admin_console_repo,
        "list_questionnaire_external_push_log_threads",
        lambda *args, **kwargs: [dict(row)],
    )
    monkeypatch.setattr(
        queries.admin_console_repo,
        "count_questionnaire_external_push_logs",
        lambda **kwargs: 1,
    )
    monkeypatch.setattr(
        queries.questionnaire_domain_service,
        "is_questionnaire_external_push_global_enabled",
        lambda: True,
    )

    class FakeListQuestionnairesQuery:
        def __call__(self):
            return [{"external_push_enabled": True}]

    monkeypatch.setattr(queries, "ListQuestionnairesQuery", FakeListQuestionnairesQuery)

    payload = queries.GetGlobalQuestionnaireExternalPushLogsQuery()()

    assert payload["logs"][0]["questionnaire_path"] == "/admin/questionnaires/21"
    assert payload["logs"][0]["questionnaire_logs_path"] == "/admin/questionnaires/21/external-push-logs"
