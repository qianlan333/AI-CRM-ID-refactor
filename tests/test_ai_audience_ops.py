from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from aicrm_next.channel_entry.application import _ai_audience_channel_entry_only_enabled
from aicrm_next.ai_audience_ops.event_types import MEMBER_EVENT_PREFIX, OUTBOUND_EFFECT_CONSUMER
from aicrm_next.ai_audience_ops.repository import next_daily_refresh_at
from aicrm_next.ai_audience_ops.service import AudiencePackageService
from aicrm_next.ai_audience_ops.sql_linter import lint_sql
from aicrm_next.platform_foundation.external_effects import WEBHOOK_GENERIC_PUSH
from aicrm_next.platform_foundation.internal_events.worker import InternalEventWorker
from aicrm_next.shared.db_session import get_session_factory


TOKEN = "ai-audience-test-token"


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def _valid_incremental_sql() -> str:
    return """
        SELECT
            'external_userid' AS identity_type,
            external_userid AS identity_value,
            'questionnaire_submission:' || submission_id::text AS event_source_key,
            payload_json,
            external_userid,
            owner_userid,
            submitted_at AS event_at
        FROM audience_read.questionnaire_submissions_v1
        WHERE questionnaire_id = :questionnaire_id
          AND submitted_at >= :last_watermark_at
          AND submitted_at < :refresh_started_at
    """


def test_sql_linter_blocks_dangerous_and_non_catalog_sql() -> None:
    assert "keyword_forbidden:drop" in lint_sql("DROP TABLE users").errors
    assert "select_star_forbidden" in lint_sql("SELECT * FROM audience_read.orders_v1").errors
    result = lint_sql(
        "SELECT 'external_userid' AS identity_type, external_userid AS identity_value, external_userid AS event_source_key, '{}'::jsonb AS payload_json FROM public.users"
    )
    assert "dependency_not_allowed:public.users" in result.errors


def test_next_daily_refresh_uses_package_timezone_and_time() -> None:
    after = datetime(2026, 6, 22, 20, 5, tzinfo=timezone.utc)

    assert next_daily_refresh_at("03:00", "Asia/Shanghai", after=after) == datetime(2026, 6, 23, 19, 0, tzinfo=timezone.utc)


def test_channel_entry_ai_audience_only_flag(monkeypatch) -> None:
    monkeypatch.setattr("aicrm_next.channel_entry.application.runtime_bool", lambda key: key == "AICRM_AI_AUDIENCE_CHANNEL_ENTRY_ONLY")

    assert _ai_audience_channel_entry_only_enabled() is True


def test_publish_requires_sql_for_enabled_refresh_modes() -> None:
    class Repo:
        def get_package(self, package_id):
            return {"id": package_id, "incremental_enabled": True, "daily_enabled": True}

        def get_current_version(self, package_id):
            return {"id": 9, "incremental_sql_text": _valid_incremental_sql(), "snapshot_sql_text": ""}

        def update_version_validation(self, *args, **kwargs):
            return {}

    result = AudiencePackageService(repository=Repo(), internal_events=object()).publish(1)

    assert result["ok"] is False
    assert result["error"] == "sql_validation_failed"
    assert "snapshot_sql_required" in result["validation_errors"]


@pytest.mark.usefixtures("next_pg_schema")
def test_package_refresh_uses_internal_event_and_external_effect_queue(next_client, monkeypatch) -> None:
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AICRM_AUDIENCE_READONLY_DATABASE_URL", database_url)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ENABLED", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_AUTO_EXECUTE", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE", "5")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS", f"{MEMBER_EVENT_PREFIX}entered:{OUTBOUND_EFFECT_CONSUMER}")

    session_factory = get_session_factory()
    with session_factory() as session:
        session.execute(
            text(
                """
                INSERT INTO questionnaire_submissions (
                    questionnaire_id, respondent_key, external_userid, staff_id, submitted_at
                )
                VALUES (101, 'rk_1', 'wm_ai_audience_001', 'HuangYouCan', CURRENT_TIMESTAMP - interval '1 minute')
                """
            )
        )
        session.commit()

    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={
            "package_key": "q101_submitted_added_wecom",
            "name": "提交 101 问卷且已加微",
            "natural_language_definition": "提交 101 问卷",
            "query_mode": "incremental_event",
            "incremental_sql_text": _valid_incremental_sql(),
        },
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["package"]["id"]

    publish_resp = next_client.post(f"/api/ai/audience/packages/{package_id}/publish", headers=_auth(), json={})
    assert publish_resp.status_code == 200
    assert publish_resp.json()["ok"] is True

    sub_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/outbound-subscriptions",
        headers=_auth(),
        json={"trigger_event_type": "entered", "webhook_url": "https://agent.example.test/audience"},
    )
    assert sub_resp.status_code == 200

    refresh_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/refresh",
        headers=_auth(),
        json={"run_type": "incremental", "params": {"questionnaire_id": 101}},
    )
    assert refresh_resp.status_code == 200
    body = refresh_resp.json()
    assert body["ok"] is True
    assert body["entered_count"] == 1
    assert body["member_event_count"] == 1

    worker_result = InternalEventWorker().run_due(
        batch_size=5,
        dry_run=False,
        event_types=[f"{MEMBER_EVENT_PREFIX}entered"],
        consumer_names=[OUTBOUND_EFFECT_CONSUMER],
    )
    assert worker_result["counts"]["succeeded_count"] == 1

    effects_resp = next_client.get(f"/api/ai/audience/packages/{package_id}/external-effects", headers=_auth())
    assert effects_resp.status_code == 200
    jobs = effects_resp.json()["external_effect_jobs"]
    assert len(jobs) == 1
    assert jobs[0]["effect_type"] == WEBHOOK_GENERIC_PUSH
    assert jobs[0]["business_type"] == "ai_audience_member_event"


@pytest.mark.usefixtures("next_pg_schema")
def test_source_dirty_emits_existing_internal_event_queue(next_client, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)
    response = next_client.post(
        "/api/ai/audience/source-dirty",
        headers=_auth(),
        json={
            "source_type": "questionnaire_submission",
            "source_key": "questionnaire:101",
            "identity_type": "external_userid",
            "identity_value": "wm_dirty",
            "occurred_at": "2026-06-23T10:00:00+08:00",
            "payload": {"submission_id": 123},
        },
    )
    assert response.status_code == 200
    assert response.json()["event"]["event_type"] == "ai_audience.source.changed"


@pytest.mark.usefixtures("next_pg_schema")
def test_inbound_webhook_requires_hmac_and_records_event(next_client, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)
    secret = "inbound-secret"
    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={
            "package_key": "agent_callback_pkg",
            "name": "Agent 回调包",
            "inbound_webhook_secret": secret,
        },
    )
    assert create_resp.status_code == 200
    payload = {
        "external_event_id": "agent_run_abc",
        "member_event_id": 1,
        "status": "generated",
        "message": {"text": "hello"},
        "action": {"type": "record_only"},
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    response = next_client.post(
        "/api/ai/audience/packages/agent_callback_pkg/webhook",
        content=raw,
        headers={"X-AICRM-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["record_only"] is True
