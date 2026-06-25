from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy import text

from aicrm_next.automation_agents.context_builder import referenced_context_keys
from aicrm_next.automation_agents.worker import AutomationAgentWorker
from aicrm_next.shared.db_session import get_session_factory


def _insert_package(session, *, package_key: str = "agent_callback_pkg", secret: str = "callback-secret") -> int:
    row = session.execute(
        text(
            """
            INSERT INTO ai_audience_package (
                package_key, name, status, inbound_webhook_secret, created_at, updated_at
            )
            VALUES (:package_key, 'Agent Callback Package', 'active', :secret, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """
        ),
        {"package_key": package_key, "secret": secret},
    ).mappings().one()
    return int(row["id"])


def _insert_agent(session, *, agent_code: str = "activation_agent", status: str = "active", package_key: str = "agent_callback_pkg", secret: str = "agent-secret") -> int:
    row = session.execute(
        text(
            """
            INSERT INTO automation_agent_runtime_config (
                agent_code, agent_name, bound_package_key, status,
                draft_role_prompt, draft_task_prompt, published_role_prompt, published_task_prompt,
                draft_version, published_version, fixed_content_package_json, inbound_webhook_secret,
                created_at, updated_at
            )
            VALUES (
                :agent_code, '激活 Agent', :package_key, :status,
                '你是助手，参考{{用户标签}}', '输出话术：{{最近20条聊天信息}}', '你是助手，参考{{用户标签}}', '输出话术：{{最近20条聊天信息}}',
                1, 1, '{"image_library_ids":[12],"miniprogram_library_ids":[],"attachment_library_ids":[],"content_text":""}'::jsonb, :secret,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id
            """
        ),
        {"agent_code": agent_code, "package_key": package_key, "status": status, "secret": secret},
    ).mappings().one()
    return int(row["id"])


def _signature(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _count(table: str) -> int:
    with get_session_factory()() as session:
        return int(session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)


def test_agent_webhook_accepts_array_dedupes_and_requires_hmac(next_client, next_pg_schema) -> None:
    with get_session_factory()() as session:
        _insert_package(session)
        _insert_agent(session)
        session.commit()

    raw = json.dumps(["wm_001", "", "wm_001", "wm_002"], ensure_ascii=False, separators=(",", ":")).encode()
    missing = next_client.post("/api/ai/agents/activation_agent/audience-webhook", content=raw, headers={"Content-Type": "application/json"})
    assert missing.status_code == 401
    assert missing.json()["error"] == "missing_signature"

    invalid = next_client.post(
        "/api/ai/agents/activation_agent/audience-webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-AICRM-Signature": "bad"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["error"] == "invalid_signature"

    accepted = next_client.post(
        "/api/ai/agents/activation_agent/audience-webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-AICRM-Signature": _signature("agent-secret", raw),
            "X-AICRM-Event-Type": "audience.entered",
            "X-AICRM-Idempotency-Key": "dedupe-key-1",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["mode"] == "queued"
    assert accepted.json()["received_count"] == 4
    assert accepted.json()["deduped_count"] == 2
    assert accepted.json()["accepted_count"] == 2
    assert _count("automation_agent_webhook_batch") == 1
    assert _count("automation_agent_webhook_item") == 2

    replay = next_client.post(
        "/api/ai/agents/activation_agent/audience-webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-AICRM-Signature": _signature("agent-secret", raw), "X-AICRM-Idempotency-Key": "dedupe-key-1"},
    )
    assert replay.status_code == 200
    assert _count("automation_agent_webhook_batch") == 1
    assert _count("automation_agent_webhook_item") == 2


def test_agent_webhook_rejects_inactive_and_large_payload(next_client, next_pg_schema) -> None:
    with get_session_factory()() as session:
        _insert_package(session)
        _insert_agent(session, agent_code="paused_agent", status="paused")
        _insert_agent(session, agent_code="large_agent")
        session.commit()

    raw = b'{"external_userids":["wm_001"]}'
    paused = next_client.post(
        "/api/ai/agents/paused_agent/audience-webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-AICRM-Signature": _signature("agent-secret", raw)},
    )
    assert paused.status_code == 409
    assert paused.json()["error"] == "agent_not_active"

    large_payload = {"external_userids": [f"wm_{i:03d}" for i in range(201)]}
    large_raw = json.dumps(large_payload, separators=(",", ":")).encode()
    large = next_client.post(
        "/api/ai/agents/large_agent/audience-webhook",
        content=large_raw,
        headers={"Content-Type": "application/json", "X-AICRM-Signature": _signature("agent-secret", large_raw)},
    )
    assert large.status_code == 400
    assert large.json()["error"] == "too_many_external_userids"


def test_prompt_context_key_detection_uses_chinese_placeholders() -> None:
    assert referenced_context_keys("角色{{用户标签}}", "任务{{问卷信息}}{{激活信息}}") == {"tags", "questionnaire", "activation"}
    assert referenced_context_keys("无占位", "只看{{最近20条聊天信息}}") == {"recent_messages"}


def test_worker_fake_mode_generates_package_and_enqueues_send_plan(next_client, next_pg_schema, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AI_AUDIENCE_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_AGENT_FAKE_ALLOWED", "1")
    monkeypatch.setenv("AICRM_AI_AUDIENCE_AGENT_FAKE_OUTPUT", "你好，这是 Agent 生成的话术")

    with get_session_factory()() as session:
        _insert_package(session, secret="callback-secret")
        _insert_agent(session)
        session.commit()

    raw = b'{"external_userids":["wm_001"]}'
    accepted = next_client.post(
        "/api/ai/agents/activation_agent/audience-webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-AICRM-Signature": _signature("agent-secret", raw)},
    )
    batch_id = accepted.json()["batch_id"]

    from aicrm_next.automation_agents import worker as worker_module

    seen_keys = {}

    def fake_context(external_userid, referenced_keys):
        seen_keys["keys"] = set(referenced_keys)
        return {
            "owner_userid": "owner_001",
            "customer": {"external_userid": external_userid, "owner_userid": "owner_001"},
            "recent_messages": [{"sender": external_userid, "content": "我想了解课程", "send_time": "2026-06-25 10:00"}],
            "tags": ["高意向"],
            "blocks": {"用户标签": "高意向", "最近20条聊天信息": "2026-06-25 10:00 wm_001: 我想了解课程"},
            "referenced_context_keys": sorted(referenced_keys),
        }

    monkeypatch.setattr(worker_module, "build_agent_context", fake_context)

    result = AutomationAgentWorker().run_batch(batch_id)

    assert result["status"] == "succeeded"
    assert seen_keys["keys"] == {"tags", "recent_messages"}
    with get_session_factory()() as session:
        item = session.execute(text("SELECT * FROM automation_agent_webhook_item")).mappings().one()
        plan_count = int(session.execute(text("SELECT COUNT(*) FROM cloud_broadcast_plans")).scalar() or 0)
        message = session.execute(text("SELECT * FROM cloud_broadcast_plan_recipient_messages")).mappings().one()
        effect_count = int(session.execute(text("SELECT COUNT(*) FROM external_effect_job WHERE effect_type = 'WECOM_MESSAGE_PRIVATE_SEND'")).scalar() or 0)
    assert item["status"] == "callback_succeeded"
    assert item["owner_userid"] == "owner_001"
    assert item["content_package_json"]["content_text"] == "你好，这是 Agent 生成的话术"
    assert item["content_package_json"]["image_library_ids"] == [12]
    assert plan_count == 1
    assert message["content_text"] == "你好，这是 Agent 生成的话术"
    assert effect_count == 0

