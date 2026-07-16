from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from psycopg.rows import dict_row

from aicrm_next.channel_entry import application as channel_application
from aicrm_next.channel_entry import identity_external_effect
from aicrm_next.channel_entry import repo as channel_repo
from aicrm_next.channel_entry.application import process_wecom_external_contact_event
from aicrm_next.channel_entry.schemas import ProcessWeComExternalContactEventCommand
from aicrm_next.customer_read_model.refresh_intents import (
    CUSTOMER_REFRESH_REQUESTED_EVENT,
    CustomerReadModelRefreshIntentRepository,
    CustomerReadModelRefreshIntentService,
)
from aicrm_next.platform_foundation.external_effects.adapters import WeComExternalContactDetailAdapter
from aicrm_next.platform_foundation.external_effects.continuations import ExternalEffectContinuationRegistry
from aicrm_next.platform_foundation.external_effects.repo import SQLAlchemyExternalEffectRepository


pytestmark = pytest.mark.usefixtures("next_pg_schema")


def _database_url() -> str:
    return str(os.environ.get("DATABASE_URL") or os.environ.get("AICRM_TEST_DATABASE_URL") or "")


def _connect(*, autocommit: bool = True):
    return psycopg.connect(_database_url(), autocommit=autocommit, row_factory=dict_row)


def _identity_plan(external_userid: str = "wm_event_driven_001") -> dict:
    return channel_repo.enqueue_channel_entry_identity_resolution(
        corp_id="ww-event-driven",
        external_userid=external_userid,
        follow_user_userid="owner-event-driven",
        payload_json={
            "Event": "change_external_contact",
            "ChangeType": "add_external_contact",
            "ExternalUserID": external_userid,
            "UserID": "owner-event-driven",
            "corp_id": "ww-event-driven",
        },
        reason="postgres_event_driven_test",
        event_log_id=8101,
    )


def test_callback_persists_one_identity_effect_without_inline_provider(monkeypatch) -> None:
    provider_calls: list[str] = []
    status_updates: list[tuple[int, str]] = []
    monkeypatch.setattr(
        channel_application.repo,
        "log_external_contact_event",
        lambda **kwargs: {"id": 8101, **kwargs},
    )
    monkeypatch.setattr(
        channel_application.repo,
        "mark_event_status",
        lambda event_id, status, error_message="": status_updates.append((event_id, status)),
    )
    monkeypatch.setattr(
        channel_application,
        "sync_external_contact_identity_for_event",
        lambda *args, **kwargs: provider_calls.append("provider") or {},
    )
    command = ProcessWeComExternalContactEventCommand(
        corp_id="ww-event-driven",
        event_data={
            "Event": "change_external_contact",
            "ChangeType": "add_external_contact",
            "ExternalUserID": "wm_callback_event_driven",
            "UserID": "owner-event-driven",
            "CreateTime": "1781800001",
        },
        payload_xml="<xml/>",
        route="/wecom/external-contact/callback",
    )

    first = process_wecom_external_contact_event(command)
    second = process_wecom_external_contact_event(command)

    with _connect() as connection:
        queue_rows = connection.execute(
            """
            SELECT id, status, lane, execution_id, external_effect_job_id
            FROM crm_user_identity_resolution_queue
            WHERE source_type = 'channel_entry'
              AND external_userid = 'wm_callback_event_driven'
            """
        ).fetchall()
        effect_rows = connection.execute(
            """
            SELECT id, effect_type, lane, status, execution_id, parent_execution_id,
                   payload_summary_json
            FROM external_effect_job
            WHERE effect_type = 'wecom.external_contact.detail.fetch'
              AND target_id = 'wm_callback_event_driven'
            """
        ).fetchall()

    assert first["identity_sync"]["status"] == "queued"
    assert second["identity_sync"]["external_effect_job_id"] == first["identity_sync"]["external_effect_job_id"]
    assert provider_calls == []
    assert len(queue_rows) == len(effect_rows) == 1
    assert queue_rows[0]["status"] == "pending"
    assert queue_rows[0]["lane"] == effect_rows[0]["lane"] == "wecom_interactive"
    assert queue_rows[0]["external_effect_job_id"] == effect_rows[0]["id"]
    assert effect_rows[0]["parent_execution_id"] == queue_rows[0]["execution_id"]
    assert effect_rows[0]["status"] == "queued"
    assert effect_rows[0]["payload_summary_json"]["external_userid_present"] is True
    assert "wm_callback_event_driven" not in json.dumps(effect_rows[0]["payload_summary_json"])
    assert status_updates == [(8101, "success"), (8101, "success")]


class _Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_external_contact_detail(self, external_userid: str) -> dict:
        self.calls.append(external_userid)
        return {
            "errcode": 0,
            "errmsg": "ok",
            "external_contact": {
                "external_userid": external_userid,
                "unionid": "union_private_result_001",
                "openid": "openid_private_result_001",
                "name": "敏感客户姓名",
                "type": 1,
            },
            "follow_user": [
                {
                    "userid": "owner-event-driven",
                    "remark": "敏感备注",
                    "description": "敏感描述",
                    "createtime": 1781800002,
                }
            ],
        }


class _FailingIdentityBridge:
    def apply_external_contact_detail(self, **kwargs):
        raise RuntimeError("local identity projection unavailable")


class _SuccessfulIdentityBridge:
    def __init__(self) -> None:
        self.calls = 0

    def apply_external_contact_detail(self, **kwargs):
        self.calls += 1
        assert kwargs["detail_payload"]["external_contact"]["name"] == "敏感客户姓名"
        return {
            "status": "success",
            "unionid": "union_private_result_001",
            "identity_map_id": 991,
            "openid_present": True,
            "provider_result_applied": True,
            "real_external_call_executed": False,
        }


def test_provider_result_is_private_and_continuation_failure_cannot_pollute_provider_success(monkeypatch) -> None:
    planned = _identity_plan("wm_private_result_001")
    job_id = int(planned["external_effect_job_id"])
    with _connect() as connection:
        connection.execute(
            """
            UPDATE external_effect_job
            SET status = 'dispatching', lease_token = 'lease-private-result',
                lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes',
                heartbeat_at = CURRENT_TIMESTAMP, locked_by = 'pytest',
                locked_at = CURRENT_TIMESTAMP, worker_generation = 9
            WHERE id = %s
            """,
            (job_id,),
        )

    repository = SQLAlchemyExternalEffectRepository()
    leased = repository.get_job(job_id)
    assert leased is not None
    provider = _Provider()
    adapter = WeComExternalContactDetailAdapter(adapter_factory=lambda: provider)
    dispatch_result = adapter.dispatch(leased)
    public_dispatch = json.dumps(
        {
            "request": dispatch_result.request_summary,
            "response": dispatch_result.response_summary,
        },
        ensure_ascii=False,
    )
    for secret in (
        "wm_private_result_001",
        "union_private_result_001",
        "openid_private_result_001",
        "敏感客户姓名",
        "敏感备注",
        "敏感描述",
    ):
        assert secret not in public_dispatch
    assert dispatch_result.response_summary == {
        "errcode": 0,
        "provider_detail_present": True,
        "follow_user_count": 1,
        "real_external_call_executed": True,
        "provider_result_received": True,
    }

    begun = repository.begin_provider_attempt(job=leased, request_summary=dispatch_result.request_summary)
    assert begun is not None
    dispatching_job, _ = begun
    completed = repository.complete_dispatch(job=dispatching_job, result=dispatch_result)
    assert completed is not None
    completed_job, public_attempt = completed
    assert completed_job.status == public_attempt.status == "succeeded"
    assert provider.calls == ["wm_private_result_001"]

    public_attempt_json = json.dumps(public_attempt.to_dict(), ensure_ascii=False)
    for secret in (
        "union_private_result_001",
        "openid_private_result_001",
        "敏感客户姓名",
        "敏感备注",
        "敏感描述",
    ):
        assert secret not in public_attempt_json
    with _connect() as connection:
        private_attempt = connection.execute(
            """
            SELECT status, provider_result_json, provider_result_hash,
                   request_summary_json, response_summary_json
            FROM external_effect_attempt
            WHERE attempt_id = %s
            """,
            (public_attempt.attempt_id,),
        ).fetchone()
    assert private_attempt["provider_result_json"]["external_contact"]["name"] == "敏感客户姓名"
    assert len(private_attempt["provider_result_hash"]) == 64
    assert "敏感客户姓名" not in json.dumps(private_attempt["request_summary_json"], ensure_ascii=False)
    assert "敏感客户姓名" not in json.dumps(private_attempt["response_summary_json"], ensure_ascii=False)

    continuation_registry = ExternalEffectContinuationRegistry(
        (identity_external_effect.IDENTITY_EXTERNAL_CONTACT_DETAIL_CONTINUATION,)
    )
    monkeypatch.setattr(identity_external_effect, "build_identity_bridge_service", lambda: _FailingIdentityBridge())
    failed = continuation_registry.run(completed_job, dispatch_result)
    assert failed["ok"] is False
    with _connect() as connection:
        failure_state = connection.execute(
            """
            SELECT job.status AS job_status, attempt.status AS attempt_status,
                   attempt.provider_result_json,
                   (SELECT COUNT(*) FROM identity_resolution_completion_receipt) AS receipt_count
            FROM external_effect_job job
            JOIN external_effect_attempt attempt ON attempt.job_id = job.id
            WHERE job.id = %s
            """,
            (job_id,),
        ).fetchone()
    assert failure_state["job_status"] == failure_state["attempt_status"] == "succeeded"
    assert failure_state["provider_result_json"]["external_contact"]["unionid"] == "union_private_result_001"
    assert failure_state["receipt_count"] == 0

    successful_bridge = _SuccessfulIdentityBridge()
    monkeypatch.setattr(identity_external_effect, "build_identity_bridge_service", lambda: successful_bridge)
    monkeypatch.setattr(channel_application, "_record_identity_sync_result", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        channel_application,
        "_canonicalize_channel_entry_after_identity",
        lambda *args, **kwargs: {"status": "success"},
    )
    monkeypatch.setattr(identity_external_effect, "_emit_identity_resolved", lambda **kwargs: {"ok": True})

    first = continuation_registry.run(completed_job, dispatch_result)
    second = continuation_registry.run(completed_job, dispatch_result)
    assert first["ok"] is second["ok"] is True
    assert first["provider_result_consumed"] is True
    assert second["deduplicated"] is True
    assert successful_bridge.calls == 1

    with _connect() as connection:
        final_state = connection.execute(
            """
            SELECT job.status AS job_status, queue.status AS queue_status,
                   attempt.provider_result_json, attempt.provider_result_consumed_at,
                   (SELECT COUNT(*) FROM identity_resolution_completion_receipt) AS receipt_count
            FROM external_effect_job job
            JOIN external_effect_attempt attempt ON attempt.job_id = job.id
            JOIN crm_user_identity_resolution_queue queue ON queue.external_effect_job_id = job.id
            WHERE job.id = %s
            """,
            (job_id,),
        ).fetchone()
    assert final_state["job_status"] == "succeeded"
    assert final_state["queue_status"] == "resolved"
    assert final_state["provider_result_json"] == {}
    assert final_state["provider_result_consumed_at"] is not None
    assert final_state["receipt_count"] == 1
    assert repository.get_attempt_provider_result(public_attempt.attempt_id) == {}


def test_customer_refresh_coalesces_sources_and_preserves_dirty_during_run() -> None:
    repository = CustomerReadModelRefreshIntentRepository()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda key: repository.mark_dirty(
                    source_event_key=key,
                    source_event_type="identity.resolved",
                    parent_execution_id=f"exe_source_{key[-1]}",
                ),
                ("evt-customer-source-1", "evt-customer-source-2"),
            )
        )

    assert sorted(result["generation"] for result in results) == [1, 2]
    assert sum(bool(result["signal_created"]) for result in results) == 1
    with _connect() as connection:
        initial = connection.execute(
            "SELECT * FROM customer_read_model_refresh_intent WHERE singleton_id = 1"
        ).fetchone()
        initial_signals = connection.execute(
            "SELECT COUNT(*) AS count FROM internal_event_outbox WHERE event_type = %s",
            (CUSTOMER_REFRESH_REQUESTED_EVENT,),
        ).fetchone()["count"]
    assert initial["dirty_generation"] == 2
    assert initial["signal_generation"] in {1, 2}
    assert initial["status"] == "waiting"
    assert initial_signals == 1

    claimed = repository.claim_latest(
        signal_generation=int(initial["signal_generation"]),
        owner_consumer_run_id=9201,
        owner_lease_token="lease-customer-1",
    )
    assert claimed["claimed"] is True
    assert claimed["running_generation"] == 2
    dirty_while_running = repository.mark_dirty(
        source_event_key="evt-customer-source-3",
        source_event_type="questionnaire.submitted",
        parent_execution_id="exe_source_3",
    )
    assert dirty_while_running["generation"] == 3
    assert dirty_while_running["signal_created"] is False

    stale = repository.complete(
        generation=2,
        result={"source_count": 10, "target_count_after": 10, "duration_ms": 11},
        owner_consumer_run_id=9201,
        owner_lease_token="stale-lease",
    )
    assert stale == {"ok": True, "completed": False, "reason": "stale_completion"}
    completed = repository.complete(
        generation=2,
        result={"source_count": 10, "target_count_after": 10, "duration_ms": 11},
        owner_consumer_run_id=9201,
        owner_lease_token="lease-customer-1",
    )
    assert completed["completed"] is True
    assert completed["continuation_created"] is True

    with _connect() as connection:
        final = connection.execute(
            "SELECT * FROM customer_read_model_refresh_intent WHERE singleton_id = 1"
        ).fetchone()
        signal_count = connection.execute(
            "SELECT COUNT(*) AS count FROM internal_event_outbox WHERE event_type = %s",
            (CUSTOMER_REFRESH_REQUESTED_EVENT,),
        ).fetchone()["count"]
    assert final["dirty_generation"] == 3
    assert final["completed_generation"] == 2
    assert final["signal_generation"] == 3
    assert final["status"] == "waiting"
    assert signal_count == 2


def test_customer_refresh_request_is_intent_only_until_internal_consumer() -> None:
    refresh_calls: list[bool] = []
    service = CustomerReadModelRefreshIntentService(
        refresh_runner=lambda *, dry_run: refresh_calls.append(dry_run)
        or {
            "ok": True,
            "source_count": 4,
            "target_count_before": 3,
            "target_count_after": 4,
            "duration_ms": 5,
        }
    )

    requested = service.request_refresh(
        source_event_key="evt-intent-only",
        source_event_type="payment.succeeded",
        parent_execution_id="exe_payment_parent",
    )
    assert requested["signal_created"] is True
    assert refresh_calls == []

    processed = service.process_requested(
        signal_generation=int(requested["generation"]),
        owner_consumer_run_id=9301,
        owner_lease_token="lease-customer-consumer",
    )
    assert processed["ok"] is True
    assert processed["completion"]["completed"] is True
    assert refresh_calls == [False]

