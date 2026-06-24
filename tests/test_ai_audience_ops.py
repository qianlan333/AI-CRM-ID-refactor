from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from aicrm_next.ai_audience_ops.event_types import (
    DAILY_REFRESH_CONSUMER,
    DAILY_TICK_EVENT,
    INCREMENTAL_REFRESH_CONSUMER,
    INCREMENTAL_TICK_EVENT,
    MEMBER_EVENT_PREFIX,
    OUTBOUND_EFFECT_CONSUMER,
    SOURCE_CHANGED_EVENT,
    SOURCE_POKE_CONSUMER,
)
from aicrm_next.ai_audience_ops.outbound_service import AudienceOutboundService
from aicrm_next.ai_audience_ops.repository import next_daily_refresh_at
from aicrm_next.ai_audience_ops.scheduler import ai_audience_event_consumer_pairs, emit_due_ticks
from aicrm_next.ai_audience_ops.service import AudiencePackageService
from aicrm_next.ai_audience_ops.sql_linter import lint_sql
from aicrm_next.ai_audience_ops.test_agent_service import AudienceTestAgentService, TEST_AGENT_MESSAGE_TEXT
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_GENERIC_PUSH, WECOM_MESSAGE_PRIVATE_SEND
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


def _valid_snapshot_sql(*, include_test_user: bool = True) -> str:
    suffix = "" if include_test_user else " AND 1 = 0"
    return f"""
        SELECT
            'external_userid' AS identity_type,
            wc.external_userid AS identity_value,
            'daily_snapshot:' || wc.external_userid AS event_source_key,
            wc.payload_json AS payload_json,
            wc.external_userid,
            wc.owner_userid,
            wc.updated_at AS event_at
        FROM audience_read.wecom_contacts_v1 wc
        WHERE wc.external_userid = :test_external_userid
        {suffix}
    """


def _external_effect_signature(secret: str, payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


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


def test_ai_audience_scheduler_emits_incremental_every_run_and_daily_only_in_2am_window() -> None:
    class Service:
        def emit_tick(self, tick_type):
            return {"ok": True, "tick_type": tick_type}

    inside_window = datetime(2026, 6, 24, 2, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    outside_window = datetime(2026, 6, 24, 1, 59, tzinfo=ZoneInfo("Asia/Shanghai"))

    from aicrm_next.ai_audience_ops import scheduler as scheduler_module

    original = scheduler_module.AudiencePackageService
    scheduler_module.AudiencePackageService = lambda: Service()
    try:
        due = emit_due_ticks(now=inside_window, daily_refresh_time="02:00", daily_window_minutes=60)
        not_due = emit_due_ticks(now=outside_window, daily_refresh_time="02:00", daily_window_minutes=60)
    finally:
        scheduler_module.AudiencePackageService = original

    assert [item["tick_type"] for item in due["items"]] == ["incremental", "daily"]
    assert due["daily_tick_due"] is True
    assert [item["tick_type"] for item in not_due["items"]] == ["incremental"]
    assert not_due["daily_tick_due"] is False


def test_ai_audience_scheduler_consumer_pairs_cover_source_refresh_and_outbound() -> None:
    pairs = ai_audience_event_consumer_pairs()

    assert f"{SOURCE_CHANGED_EVENT}:{SOURCE_POKE_CONSUMER}" in pairs
    assert f"{INCREMENTAL_TICK_EVENT}:{INCREMENTAL_REFRESH_CONSUMER}" in pairs
    assert f"{DAILY_TICK_EVENT}:{DAILY_REFRESH_CONSUMER}" in pairs
    assert f"{MEMBER_EVENT_PREFIX}entered:{OUTBOUND_EFFECT_CONSUMER}" in pairs
    assert f"{MEMBER_EVENT_PREFIX}updated:{OUTBOUND_EFFECT_CONSUMER}" in pairs
    assert f"{MEMBER_EVENT_PREFIX}exited:{OUTBOUND_EFFECT_CONSUMER}" in pairs


def test_publish_requires_sql_for_enabled_refresh_modes() -> None:
    class Repo:
        def get_package(self, package_id):
            return {"id": package_id, "incremental_enabled": True, "daily_enabled": True}

        def get_latest_version(self, package_id):
            return {"id": 9, "incremental_sql_text": _valid_incremental_sql(), "snapshot_sql_text": ""}

        def update_version_validation(self, *args, **kwargs):
            return {}

    result = AudiencePackageService(repository=Repo(), internal_events=object()).publish(1)

    assert result["ok"] is False
    assert result["error"] == "sql_validation_failed"
    assert "snapshot_sql_required" in result["validation_errors"]


@pytest.mark.usefixtures("next_pg_schema")
def test_publish_defaults_to_latest_version(next_client, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)

    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={
            "package_key": "publish_latest_pkg",
            "name": "发布 latest 测试",
            "incremental_sql_text": _valid_incremental_sql(),
        },
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["package"]["id"]
    v1_id = create_resp.json()["version"]["id"]

    publish_v1 = next_client.post(f"/api/ai/audience/packages/{package_id}/publish", headers=_auth(), json={})
    assert publish_v1.status_code == 200

    v2_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/versions",
        headers=_auth(),
        json={"incremental_sql_text": _valid_incremental_sql() + "\n-- version 2\n"},
    )
    assert v2_resp.status_code == 200
    v2_id = v2_resp.json()["version"]["id"]

    publish_latest = next_client.post(f"/api/ai/audience/packages/{package_id}/publish", headers=_auth(), json={})
    assert publish_latest.status_code == 200
    assert publish_latest.json()["version"]["id"] == v2_id
    assert publish_latest.json()["package"]["current_version_id"] == v2_id

    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                SELECT id, status
                FROM ai_audience_package_version
                WHERE package_id = :package_id
                ORDER BY id
                """
            ),
            {"package_id": package_id},
        ).mappings().all()
    statuses = {int(row["id"]): row["status"] for row in rows}
    assert statuses[v1_id] == "archived"
    assert statuses[v2_id] == "published"


@pytest.mark.usefixtures("next_pg_schema")
def test_publish_can_target_specific_version(next_client, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)

    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={
            "package_key": "publish_specific_pkg",
            "name": "指定发布测试",
            "incremental_sql_text": _valid_incremental_sql(),
        },
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["package"]["id"]
    v1_id = create_resp.json()["version"]["id"]
    v2_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/versions",
        headers=_auth(),
        json={"incremental_sql_text": _valid_incremental_sql() + "\n-- version 2\n"},
    )
    assert v2_resp.status_code == 200

    publish_v1 = next_client.post(
        f"/api/ai/audience/packages/{package_id}/publish",
        headers=_auth(),
        json={"version_id": v1_id},
    )
    assert publish_v1.status_code == 200
    assert publish_v1.json()["version"]["id"] == v1_id
    assert publish_v1.json()["package"]["current_version_id"] == v1_id


@pytest.mark.usefixtures("next_pg_schema")
def test_daily_snapshot_publish_latest_version_can_exit_member(next_client, monkeypatch) -> None:
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AICRM_AUDIENCE_READONLY_DATABASE_URL", database_url)
    test_user = "wm_daily_exit"

    session_factory = get_session_factory()
    with session_factory() as session:
        session.execute(
            text(
                """
                INSERT INTO wecom_external_contact_identity_map (
                    external_userid, follow_user_userid, name, status, updated_at
                )
                VALUES (:external_userid, 'HuangYouCan', 'Daily Exit User', 'active', CURRENT_TIMESTAMP)
                """
            ),
            {"external_userid": test_user},
        )
        session.commit()

    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={
            "package_key": "daily_snapshot_exit_pkg",
            "name": "Daily exited 测试",
            "query_mode": "hybrid",
            "incremental_enabled": False,
            "daily_enabled": True,
            "snapshot_sql_text": _valid_snapshot_sql(include_test_user=True),
        },
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["package"]["id"]
    v1_id = create_resp.json()["version"]["id"]

    publish_v1 = next_client.post(f"/api/ai/audience/packages/{package_id}/publish", headers=_auth(), json={})
    assert publish_v1.status_code == 200
    entered_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/refresh",
        headers=_auth(),
        json={"run_type": "daily", "params": {"test_external_userid": test_user}},
    )
    assert entered_resp.status_code == 200
    assert entered_resp.json()["entered_count"] == 1

    v2_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/versions",
        headers=_auth(),
        json={"snapshot_sql_text": _valid_snapshot_sql(include_test_user=False)},
    )
    assert v2_resp.status_code == 200
    v2_id = v2_resp.json()["version"]["id"]

    publish_v2 = next_client.post(f"/api/ai/audience/packages/{package_id}/publish", headers=_auth(), json={})
    assert publish_v2.status_code == 200
    assert publish_v2.json()["package"]["current_version_id"] == v2_id
    exited_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/refresh",
        headers=_auth(),
        json={"run_type": "daily", "params": {"test_external_userid": test_user}},
    )
    assert exited_resp.status_code == 200
    assert exited_resp.json()["exited_count"] == 1

    repeat_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/refresh",
        headers=_auth(),
        json={"run_type": "daily", "params": {"test_external_userid": test_user}},
    )
    assert repeat_resp.status_code == 200
    assert repeat_resp.json()["exited_count"] == 0

    with session_factory() as session:
        package_row = session.execute(
            text("SELECT current_version_id FROM ai_audience_package WHERE id = :package_id"),
            {"package_id": package_id},
        ).mappings().one()
        version_rows = session.execute(
            text("SELECT id, status FROM ai_audience_package_version WHERE package_id = :package_id ORDER BY id"),
            {"package_id": package_id},
        ).mappings().all()
        member_row = session.execute(
            text("SELECT status FROM ai_audience_member_current WHERE package_id = :package_id AND external_userid = :external_userid"),
            {"package_id": package_id, "external_userid": test_user},
        ).mappings().one()
    assert package_row["current_version_id"] == v2_id
    assert {int(row["id"]): row["status"] for row in version_rows} == {v1_id: "archived", v2_id: "published"}
    assert member_row["status"] == "exited"


def test_ai_audience_test_agent_webhook_disabled(next_client, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_AI_AUDIENCE_TEST_AGENT_ENABLED", raising=False)

    response = next_client.post("/api/ai/audience/test-agent/webhook", json={})

    assert response.status_code == 404
    assert response.json()["error"] == "test_agent_disabled"


def test_ai_audience_test_agent_service_signs_inbound_loopback(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_ENABLED", "1")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_PACKAGE_KEYS", "test_agent_pkg")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_ALLOWED_EXTERNAL_USERIDS", "wm_test_agent")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_SENDER_USERID", "HuangYouCan")
    inbound_secret = "inbound-secret"
    outbound_secret = "outbound-secret"
    inbound_calls = []

    class Repo:
        def get_package_by_key(self, package_key):
            return {"id": 11, "package_key": package_key, "inbound_webhook_secret": inbound_secret}

        def list_subscriptions(self, package_id, active_only=True, trigger_event_type=""):
            return [{"id": 21, "package_id": package_id, "signing_secret": outbound_secret}]

    class Inbound:
        def handle(self, package_key, payload, *, raw_body: bytes, signature: str = ""):
            expected = hmac.new(inbound_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            assert signature == expected
            inbound_calls.append({"package_key": package_key, "payload": payload})
            return {"ok": True, "external_effect_job_id": 7, "record_only": False, "real_external_call_executed": False}

    payload = {
        "event_type": "audience.member.entered",
        "package_key": "test_agent_pkg",
        "member_event_id": 123,
        "member": {"external_userid": "wm_test_agent"},
    }
    service = AudienceTestAgentService(repository=Repo(), inbound_service=Inbound())

    invalid_result = service.handle(payload, signature="bad-signature")
    assert invalid_result["status_code"] == 401
    assert inbound_calls == []

    result = service.handle(payload, signature=_external_effect_signature(outbound_secret, payload))
    assert result["ok"] is True
    assert result["external_effect_job_id"] == 7
    assert result["sender_userid"] == "HuangYouCan"
    assert inbound_calls[0]["package_key"] == "test_agent_pkg"
    callback = inbound_calls[0]["payload"]
    assert callback["external_event_id"] == "self_agent:test_agent_pkg:123"
    assert callback["message"]["text"] == TEST_AGENT_MESSAGE_TEXT
    assert callback["action"] == {
        "type": "send_private_message",
        "target_external_userid": "wm_test_agent",
        "sender_userid": "HuangYouCan",
    }


@pytest.mark.usefixtures("next_pg_schema")
def test_ai_audience_test_agent_webhook_guards_and_plans_private_message(next_client, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_ENABLED", "1")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_PACKAGE_KEYS", "test_agent_pkg")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_ALLOWED_EXTERNAL_USERIDS", "wm_test_agent")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_SENDER_USERID", "HuangYouCan")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_INBOUND_ACTION_EXECUTE", "1")
    inbound_secret = "inbound-secret"
    outbound_secret = "outbound-secret"

    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={
            "package_key": "test_agent_pkg",
            "name": "自测 Agent 包",
            "inbound_webhook_secret": inbound_secret,
        },
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["package"]["id"]

    sub_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/outbound-subscriptions",
        headers=_auth(),
        json={
            "trigger_event_type": "entered",
            "webhook_url": "https://www.youcangogogo.com/api/ai/audience/test-agent/webhook",
            "signing_secret": outbound_secret,
        },
    )
    assert sub_resp.status_code == 200

    payload = {
        "event_type": "audience.member.entered",
        "package_key": "test_agent_pkg",
        "package_name": "自测 Agent 包",
        "member_event_id": 123,
        "member": {
            "external_userid": "wm_test_agent",
            "owner_userid": "HuangYouCan",
        },
        "payload": {"test_case": "self_agent"},
        "idempotency_key": "ai_audience_outbound:test:123",
    }
    valid_signature = _external_effect_signature(outbound_secret, payload)

    bad_signature_resp = next_client.post(
        "/api/ai/audience/test-agent/webhook",
        json=payload,
        headers={"X-AICRM-External-Effect-Signature": "bad-signature"},
    )
    assert bad_signature_resp.status_code == 401
    assert bad_signature_resp.json()["error"] == "invalid_signature"

    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_ALLOWED_EXTERNAL_USERIDS", "wm_other")
    forbidden_resp = next_client.post(
        "/api/ai/audience/test-agent/webhook",
        json=payload,
        headers={"X-AICRM-External-Effect-Signature": valid_signature},
    )
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["error"] == "external_userid_not_allowed"
    monkeypatch.setenv("AICRM_AI_AUDIENCE_TEST_AGENT_ALLOWED_EXTERNAL_USERIDS", "wm_test_agent")

    response = next_client.post(
        "/api/ai/audience/test-agent/webhook",
        json=payload,
        headers={"X-AICRM-External-Effect-Signature": valid_signature},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["external_userid"] == "wm_test_agent"
    assert body["sender_userid"] == "HuangYouCan"
    assert body["simulated_message"] == TEST_AGENT_MESSAGE_TEXT
    assert body["record_only"] is False
    assert body["external_effect_job_id"]

    jobs, total = ExternalEffectService().list_jobs(
        {
            "effect_type": WECOM_MESSAGE_PRIVATE_SEND,
            "business_type": "ai_audience_inbound_webhook",
            "business_id": "self_agent:test_agent_pkg:123",
        },
        limit=10,
    )
    assert total == 1
    assert len(jobs) == 1
    assert jobs[0].id == body["external_effect_job_id"]
    assert jobs[0].target_id == "wm_test_agent"
    assert jobs[0].payload["owner_userid"] == "HuangYouCan"
    assert jobs[0].payload["content_text"] == TEST_AGENT_MESSAGE_TEXT

    duplicate_resp = next_client.post(
        "/api/ai/audience/test-agent/webhook",
        json=payload,
        headers={"X-AICRM-External-Effect-Signature": valid_signature},
    )
    assert duplicate_resp.status_code == 200
    assert duplicate_resp.json()["external_effect_job_id"] == body["external_effect_job_id"]
    duplicate_jobs, duplicate_total = ExternalEffectService().list_jobs(
        {
            "effect_type": WECOM_MESSAGE_PRIVATE_SEND,
            "business_type": "ai_audience_inbound_webhook",
            "business_id": "self_agent:test_agent_pkg:123",
        },
        limit=10,
    )
    assert duplicate_total == 1
    assert duplicate_jobs[0].id == body["external_effect_job_id"]


@pytest.mark.usefixtures("next_pg_schema")
def test_create_outbound_subscription_deduplicates_active_target(next_client, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)

    create_resp = next_client.post(
        "/api/ai/audience/packages",
        headers=_auth(),
        json={"package_key": "subscription_dedupe_pkg", "name": "订阅去重测试"},
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["package"]["id"]
    webhook_url = "https://agent.example.test/audience"

    first_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/outbound-subscriptions",
        headers=_auth(),
        json={
            "trigger_event_type": "entered",
            "webhook_url": webhook_url,
            "signing_secret": "secret-v1",
            "headers": {"X-Test": "v1"},
        },
    )
    assert first_resp.status_code == 200
    assert first_resp.json()["deduplicated"] is False
    first_id = first_resp.json()["subscription"]["id"]

    second_resp = next_client.post(
        f"/api/ai/audience/packages/{package_id}/outbound-subscriptions",
        headers=_auth(),
        json={
            "trigger_event_type": "entered",
            "webhook_url": webhook_url,
            "signing_secret": "secret-v2",
            "headers": {"X-Test": "v2"},
            "max_attempts": 7,
        },
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["deduplicated"] is True
    assert second_resp.json()["subscription"]["id"] == first_id
    assert second_resp.json()["subscription"]["signing_secret"] == "secret-v2"
    assert second_resp.json()["subscription"]["headers_json"] == {"X-Test": "v2"}
    assert second_resp.json()["subscription"]["max_attempts"] == 7

    session_factory = get_session_factory()
    with session_factory() as session:
        active_count = session.execute(
            text(
                """
                SELECT COUNT(*) AS count
                FROM ai_audience_outbound_subscription
                WHERE package_id = :package_id
                  AND status = 'active'
                  AND trigger_event_type = 'entered'
                  AND target_type = 'webhook'
                  AND webhook_url = :webhook_url
                """
            ),
            {"package_id": package_id, "webhook_url": webhook_url},
        ).mappings().one()["count"]
    assert active_count == 1


def test_outbound_planner_deduplicates_historical_duplicate_subscriptions() -> None:
    calls: list[dict[str, Any]] = []

    class Repo:
        def get_member_event(self, member_event_id):
            return {
                "id": member_event_id,
                "package_id": 9,
                "event_type": "entered",
                "identity_type": "external_userid",
                "identity_value": "wm_hist",
                "external_userid": "wm_hist",
                "owner_userid": "HuangYouCan",
                "payload_json": {"case": "historical_duplicate"},
                "internal_event_id": "evt_hist",
            }

        def get_package(self, package_id):
            return {"id": package_id, "package_key": "hist_dup_pkg", "name": "历史重复订阅包"}

        def list_subscriptions(self, package_id, *, active_only=False, trigger_event_type=""):
            duplicate = {
                "package_id": package_id,
                "trigger_event_type": trigger_event_type,
                "target_type": "webhook",
                "webhook_url": "https://agent.example.test/audience",
                "signing_secret": "secret",
                "execution_mode": "execute",
                "requires_approval": False,
                "max_attempts": 5,
            }
            return [{**duplicate, "id": 1}, {**duplicate, "id": 2}]

    class Effects:
        def plan_effect(self, **kwargs):
            calls.append(kwargs)
            return {"id": len(calls), "idempotency_key": kwargs["idempotency_key"]}

    result = AudienceOutboundService(repository=Repo(), external_effects=Effects()).plan_for_member_event(88)

    assert result["ok"] is True
    assert result["planned_count"] == 1
    assert len(calls) == 1
    assert calls[0]["idempotency_key"].startswith("ai_audience_outbound:9:88:entered:")
    assert calls[0]["idempotency_key"] != "ai_audience_outbound:1:88"


@pytest.mark.usefixtures("next_pg_schema")
def test_package_refresh_uses_internal_event_and_external_effect_queue(next_client, monkeypatch) -> None:
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.setenv("AICRM_AI_AUDIENCE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AICRM_AUDIENCE_READONLY_DATABASE_URL", database_url)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ENABLED", "1")
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

    with session_factory() as session:
        member_event = session.execute(
            text(
                """
                SELECT id, internal_event_id
                FROM ai_audience_member_event
                WHERE package_id = :package_id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"package_id": package_id},
        ).mappings().one()
    assert member_event["internal_event_id"]

    worker = InternalEventWorker()
    dry_run = worker.dispatch_one_consumer(
        str(member_event["internal_event_id"]),
        OUTBOUND_EFFECT_CONSUMER,
        dry_run=True,
    )
    assert dry_run["ok"] is True
    worker_result = worker.dispatch_one_consumer(
        str(member_event["internal_event_id"]),
        OUTBOUND_EFFECT_CONSUMER,
        dry_run=False,
    )
    assert worker_result["ok"] is True
    assert worker_result["counts"]["succeeded_count"] == 1
    for _ in range(2):
        repeat_result = worker.dispatch_one_consumer(
            str(member_event["internal_event_id"]),
            OUTBOUND_EFFECT_CONSUMER,
            dry_run=False,
            force=True,
            reason="test_repeat_idempotency",
        )
        assert repeat_result["ok"] is True

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
