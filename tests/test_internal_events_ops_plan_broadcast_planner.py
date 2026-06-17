from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aicrm_next.background_jobs.broadcast_queue_worker import run_broadcast_queue_worker
from aicrm_next.cloud_orchestrator.application import ApproveCloudPlanCommand
from aicrm_next.cloud_orchestrator.repository import reset_cloud_plan_fixture_state
from aicrm_next.platform_foundation.internal_events import InternalEventService, reset_internal_event_fixture_state
from aicrm_next.platform_foundation.internal_events.models import InternalEvent, InternalEventConsumerRun
from aicrm_next.platform_foundation.internal_events.ops_plan_broadcast_planner import InternalEventOpsPlanBroadcastPlannerService
from aicrm_next.platform_foundation.internal_events.worker import InternalEventWorker


class FakePlannerService:
    def __init__(self) -> None:
        self.calls = 0

    def plan_event(self, event: InternalEvent, run: InternalEventConsumerRun) -> dict[str, Any]:
        self.calls += 1
        return {
            "ok": True,
            "planner_status": "planned",
            "broadcast_job_ids": [8801],
            "created_broadcast_job_ids": [8801] if self.calls == 1 else [],
            "reused_broadcast_job_ids": [] if self.calls == 1 else [8801],
            "scheduled_for": ["2026-06-17T12:30:00+08:00"],
            "planned_count": 2,
            "queued_count": 1,
            "real_external_call_executed": False,
        }


def _enable_ops_plan_events(monkeypatch, *, event_consumers: str = "") -> None:
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ENABLED", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_OPS_PLAN_ENABLED", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_AUTO_EXECUTE", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE", "10")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES", "ops_plan.approved")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS", event_consumers)


def _emit_plan_event(monkeypatch) -> str:
    _enable_ops_plan_events(monkeypatch)
    reset_internal_event_fixture_state()
    reset_cloud_plan_fixture_state()
    result = ApproveCloudPlanCommand().execute("plan_probe", operator="pytest")
    return str(result["internal_event_id"])


def test_plan_approve_emits_internal_event(monkeypatch) -> None:
    event_id = _emit_plan_event(monkeypatch)

    events, total = InternalEventService().list_events({"event_type": "ops_plan.approved", "aggregate_id": "plan_probe"})

    assert total == 1
    assert events[0].event_id == event_id
    assert events[0].payload_summary_json["plan_type"] == "cloud_plan"


def test_allowlist_without_ops_plan_pair_does_not_execute(monkeypatch) -> None:
    event_id = _emit_plan_event(monkeypatch)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS", "payment.succeeded:order_projection_consumer")

    result = InternalEventWorker().run_due(batch_size=10, dry_run=False, event_types=["ops_plan.approved"])
    runs, _ = InternalEventService().list_consumer_runs({"event_id": event_id, "consumer_name": "broadcast_task_planner_consumer"})

    assert result["counts"]["candidate_count"] == 0
    assert runs[0].status == "pending"


def test_planner_consumer_dry_run_does_not_call_planner(monkeypatch) -> None:
    event_id = _emit_plan_event(monkeypatch)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS", "ops_plan.approved:broadcast_task_planner_consumer")
    fake = FakePlannerService()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.internal_events.shadow.build_ops_plan_broadcast_planner_service",
        lambda: fake,
    )

    result = InternalEventWorker().run_due(batch_size=10, dry_run=True, event_types=["ops_plan.approved"])
    runs, _ = InternalEventService().list_consumer_runs({"event_id": event_id, "consumer_name": "broadcast_task_planner_consumer"})

    assert result["counts"]["candidate_count"] == 1
    assert fake.calls == 0
    assert runs[0].status == "pending"


def test_planner_consumer_execute_records_broadcast_job_summary(monkeypatch) -> None:
    event_id = _emit_plan_event(monkeypatch)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS", "ops_plan.approved:broadcast_task_planner_consumer")
    fake = FakePlannerService()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.internal_events.shadow.build_ops_plan_broadcast_planner_service",
        lambda: fake,
    )

    result = InternalEventWorker().run_due(batch_size=10, dry_run=False, event_types=["ops_plan.approved"])
    runs, _ = InternalEventService().list_consumer_runs({"event_id": event_id, "consumer_name": "broadcast_task_planner_consumer"})

    assert result["counts"]["succeeded_count"] == 1
    assert fake.calls == 1
    assert runs[0].status == "succeeded"
    assert runs[0].result_summary_json["broadcast_job_ids_csv"] == "8801"
    assert runs[0].result_summary_json["scheduled_for_csv"] == "2026-06-17T12:30:00+08:00"
    assert runs[0].result_summary_json["real_external_call_executed"] is False


def test_planner_consumer_force_replay_reuses_existing_job(monkeypatch) -> None:
    event_id = _emit_plan_event(monkeypatch)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS", "ops_plan.approved:broadcast_task_planner_consumer")
    fake = FakePlannerService()
    monkeypatch.setattr(
        "aicrm_next.platform_foundation.internal_events.shadow.build_ops_plan_broadcast_planner_service",
        lambda: fake,
    )
    worker = InternalEventWorker()

    first = worker.dispatch_one_consumer(event_id, "broadcast_task_planner_consumer", dry_run=False)
    second = worker.dispatch_one_consumer(
        event_id,
        "broadcast_task_planner_consumer",
        dry_run=False,
        force=True,
        reason="gray replay test",
    )

    assert first["consumer_run"]["status"] == "succeeded"
    assert second["consumer_run"]["result_summary_json"]["broadcast_job_ids_csv"] == "8801"
    assert second["consumer_run"]["result_summary_json"]["reused_broadcast_job_ids_csv"] == "8801"


def test_postgres_planner_writes_queued_broadcast_job_with_plan_schedule(next_pg_schema) -> None:
    import psycopg
    from psycopg.rows import dict_row

    url = os.environ["DATABASE_URL"]
    plan_id = "external_daily_lesson_20260617_1230_huangyoucan_v1_b11"
    with psycopg.connect(url, row_factory=dict_row) as conn:
        plan_row = conn.execute(
            """
            INSERT INTO cloud_broadcast_plans (
                plan_id, display_name, owner_userid, candidate_count,
                review_status, run_status, status, created_at, updated_at
            )
            VALUES (%s, '12:30 日课', 'HuangYouCan', 2, 'approved', 'draft', 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING plan_id
            """,
            (plan_id,),
        ).fetchone()
        recipient_rows = []
        for external_userid in ("wm_target_a", "wm_target_b"):
            recipient_rows.append(
                conn.execute(
                    """
                    INSERT INTO cloud_broadcast_plan_recipients (
                        plan_id, external_userid, owner_userid, display_name, planned_message_count
                    )
                    VALUES (%s, %s, 'HuangYouCan', 'target', 1)
                    RETURNING id
                    """,
                    (plan_row["plan_id"], external_userid),
                ).fetchone()
            )
        for row in recipient_rows:
            conn.execute(
                """
                INSERT INTO cloud_broadcast_plan_recipient_messages (
                    plan_id, recipient_id, external_userid, sequence_index, day_offset, send_time, content_text
                )
                VALUES (%s, %s, 'redacted-in-test', 1, 0, '12:30', 'hello 12:30')
                """,
                (plan_id, row["id"]),
            )

    event = InternalEvent(
        event_id="iev_plan_pg",
        event_type="ops_plan.approved",
        aggregate_id=plan_id,
        trace_id=plan_id,
        payload_summary_json={"plan_id": plan_id, "plan_type": "cloud_plan", "target_count": 2, "operator": "pytest"},
    )
    run = InternalEventConsumerRun(event_id=event.event_id, consumer_name="broadcast_task_planner_consumer")

    result = InternalEventOpsPlanBroadcastPlannerService().plan_event(event, run)
    replay = InternalEventOpsPlanBroadcastPlannerService().plan_event(event, run)

    assert result["ok"] is True
    assert result["queued_count"] == 1
    assert result["planned_count"] == 2
    assert result["scheduled_for"] == ["2026-06-17T12:30:00+08:00"]
    assert replay["broadcast_job_ids"] == result["broadcast_job_ids"]
    with psycopg.connect(url, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT * FROM broadcast_jobs WHERE content_payload->>'plan_id' = %s", (plan_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"
    assert rows[0]["target_count"] == 2


def test_postgres_planner_blocks_target_count_mismatch_without_job(next_pg_schema) -> None:
    import psycopg
    from psycopg.rows import dict_row

    url = os.environ["DATABASE_URL"]
    plan_id = "external_daily_lesson_20260617_1230_mismatch"
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conn.execute(
            """
            INSERT INTO cloud_broadcast_plans (plan_id, display_name, owner_userid, candidate_count, review_status)
            VALUES (%s, 'mismatch', 'HuangYouCan', 2, 'approved')
            """,
            (plan_id,),
        )
        recipient = conn.execute(
            """
            INSERT INTO cloud_broadcast_plan_recipients (plan_id, external_userid, owner_userid, planned_message_count)
            VALUES (%s, 'wm_target_a', 'HuangYouCan', 1)
            RETURNING id
            """,
            (plan_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO cloud_broadcast_plan_recipient_messages (plan_id, recipient_id, external_userid, sequence_index, day_offset, send_time, content_text)
            VALUES (%s, %s, 'redacted-in-test', 1, 0, '12:30', 'hello')
            """,
            (plan_id, recipient["id"]),
        )

    event = InternalEvent(
        event_id="iev_plan_mismatch",
        event_type="ops_plan.approved",
        aggregate_id=plan_id,
        trace_id=plan_id,
        payload_summary_json={"plan_id": plan_id, "plan_type": "cloud_plan", "target_count": 2, "operator": "pytest"},
    )
    result = InternalEventOpsPlanBroadcastPlannerService().plan_event(
        event,
        InternalEventConsumerRun(event_id=event.event_id, consumer_name="broadcast_task_planner_consumer"),
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "target_count_mismatch"
    with psycopg.connect(url, row_factory=dict_row) as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM broadcast_jobs WHERE content_payload->>'plan_id' = %s", (plan_id,)).fetchone()["c"]
    assert count == 0


def test_broadcast_worker_scans_due_queued_job_and_uses_mock_dispatcher() -> None:
    class Repo:
        def __init__(self) -> None:
            self.sent = []
            self.failed = []

        def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
            return [{"id": 7, "target_external_userids": ["wm_a"], "target_count": 1}]

        def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0) -> None:
            self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count})

        def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None:
            self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type})

    class Dispatcher:
        def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True, "outbound_task_id": 99, "sent_count": int(job["target_count"])}

    repo = Repo()
    result = run_broadcast_queue_worker(repo=repo, dispatcher=Dispatcher(), now=datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc))

    assert result["claimed"] == 1
    assert repo.sent == [{"job_id": 7, "outbound_task_id": 99, "sent_count": 1, "failed_count": 0}]


def test_internal_events_template_exposes_planner_reconciliation_fields() -> None:
    body = Path("aicrm_next/platform_foundation/internal_events/templates/admin_console/internal_events.html").read_text()

    assert "业务效果核对" in body
    assert "Broadcast Planner" in body
    assert "planner_status" in body
    assert "broadcast_job_ids" in body
    assert "scheduled_for" in body
    assert "queued_count" in body
    assert "real_external_call_executed: false" in body
