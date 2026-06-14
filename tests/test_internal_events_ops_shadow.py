from __future__ import annotations

from aicrm_next.cloud_orchestrator.application import ApproveCloudPlanCommand, ApproveCloudPlanRecipientCommand
from aicrm_next.cloud_orchestrator.repository import reset_cloud_plan_fixture_state
from aicrm_next.owner_migration.application import OwnerMigrationCommand, OwnerMigrationService
from aicrm_next.platform_foundation.internal_events import InternalEventService, reset_internal_event_fixture_state


class MinimalOwnerMigrationRepo:
    source_status = "unit_test"

    def preview_owner_migration(self, *, source_owner_userid: str, target_owner_userid: str, external_userids: list[str] | None = None) -> dict:
        del source_owner_userid, target_owner_userid
        candidates = list(external_userids or ["wm_owner_a", "wm_owner_b"])
        return {
            "source_status": self.source_status,
            "candidate_count": len(candidates),
            "all_external_userids": candidates,
            "sample_external_userids": candidates[:2],
            "surface_counts": {"contacts": len(candidates)},
            "pending_review": {},
        }

    def execute_owner_migration(
        self,
        *,
        source_owner_userid: str,
        target_owner_userid: str,
        operator: str,
        external_userids: list[str] | None = None,
        target_owner_display_name: str | None = None,
    ) -> dict:
        del source_owner_userid, target_owner_userid, operator, target_owner_display_name
        touched = list(external_userids or ["wm_owner_a", "wm_owner_b"])
        return {
            "executed": True,
            "touched_count": len(touched),
            "update_counts": {"contacts": len(touched)},
            "touched_external_userids": touched,
        }

    def resolve_operation_members(self, userids: list[str]) -> dict:
        return {userid: {"user_id": userid, "display_name": userid, "status": "active"} for userid in userids}

    def lookup_customer_owners(self, external_userids: list[str]) -> dict:
        return {external_userid: {"owner_userids": ["owner_a"], "customer_name": external_userid} for external_userid in external_userids}

    def save_import_session(self, session: dict) -> None:
        del session

    def get_import_session(self, session_id: str) -> dict | None:
        del session_id
        return None

    def save_preview(self, preview: dict) -> None:
        del preview

    def get_preview(self, preview_token: str) -> dict | None:
        del preview_token
        return None

    def get_latest_preview_by_session(self, session_id: str) -> dict | None:
        del session_id
        return None

    def mark_preview_executed(self, preview_token: str, result_id: str) -> None:
        del preview_token, result_id

    def save_result(self, result: dict) -> None:
        del result

    def get_result(self, result_id: str) -> dict | None:
        del result_id
        return None

    def audit_owner_migration_event(self, event_type: str, payload: dict) -> None:
        del event_type, payload


def test_cloud_plan_approval_shadow_emits_ops_plan_approved() -> None:
    reset_internal_event_fixture_state()
    reset_cloud_plan_fixture_state()

    result = ApproveCloudPlanCommand().execute("plan_probe", operator="pytest")
    events, total = InternalEventService().list_events({"event_type": "ops_plan.approved", "aggregate_id": "plan_probe"})
    trace_events, trace_total = InternalEventService().list_events({"event_type": "ops_plan.approved", "trace_id": "plan_probe"})
    runs, run_total = InternalEventService().list_consumer_runs({"event_id": events[0].event_id})

    assert result["ok"] is True
    assert result["internal_event_status"] == "emitted"
    assert result["internal_event_id"] == events[0].event_id
    assert total == 1
    assert trace_total == 1
    assert trace_events[0].event_id == events[0].event_id
    assert events[0].aggregate_type == "cloud_orchestrator_plan"
    assert events[0].payload_summary_json == {
        "count": 2,
        "batch_id": "plan_probe",
        "operator": "pytest",
        "source": "cloud_plan",
    }
    assert run_total == 3
    assert sorted(run.consumer_name for run in runs) == [
        "ai_assist_notify_consumer",
        "audit_projection_consumer",
        "automation_schedule_refresh_consumer",
    ]


def test_cloud_plan_recipient_approval_shadow_emits_broadcast_task_created() -> None:
    reset_internal_event_fixture_state()
    reset_cloud_plan_fixture_state()
    ApproveCloudPlanCommand().execute("plan_probe", operator="pytest")

    result = ApproveCloudPlanRecipientCommand().execute("plan_probe", 1, operator="pytest")
    events, total = InternalEventService().list_events({"event_type": "broadcast_task.created", "aggregate_id": str(result["job_id"])})
    trace_events, trace_total = InternalEventService().list_events({"event_type": "broadcast_task.created", "trace_id": "plan_probe"})
    runs, run_total = InternalEventService().list_consumer_runs({"event_id": events[0].event_id})

    assert result["ok"] is True
    assert result["status"] == "approved"
    assert result["internal_event_status"] == "emitted"
    assert result["internal_event_id"] == events[0].event_id
    assert total == 1
    assert trace_total == 1
    assert trace_events[0].event_id == events[0].event_id
    assert events[0].aggregate_type == "broadcast_job"
    assert events[0].payload_summary_json == {
        "count": 1,
        "batch_id": "cloud_plan_recipient:plan_probe",
        "operator": "pytest",
        "source": "cloud_plan_recipient_approval",
    }
    assert "external_userids" not in events[0].payload_summary_json
    assert run_total == 3
    assert sorted(run.consumer_name for run in runs) == [
        "ai_assist_notify_consumer",
        "broadcast_queue_projection_consumer",
        "push_center_link_consumer",
    ]


def test_owner_migration_execute_shadow_emits_owner_migration_executed() -> None:
    reset_internal_event_fixture_state()

    result = OwnerMigrationService(MinimalOwnerMigrationRepo()).run(
        OwnerMigrationCommand(
            source_owner_userid="owner_a",
            target_owner_userid="owner_b",
            operator="pytest",
            execute=True,
            confirm=True,
            perform_wecom_transfer=False,
        )
    )
    aggregate_id = "owner_a:owner_b:pytest"
    events, total = InternalEventService().list_events({"event_type": "owner_migration.executed", "aggregate_id": aggregate_id})
    trace_events, trace_total = InternalEventService().list_events({"event_type": "owner_migration.executed", "trace_id": aggregate_id})
    runs, run_total = InternalEventService().list_consumer_runs({"event_id": events[0].event_id})

    assert result["ok"] is True
    assert result["mode"] == "execute"
    assert result["internal_event_status"] == "emitted"
    assert result["internal_event_id"] == events[0].event_id
    assert total == 1
    assert trace_total == 1
    assert trace_events[0].event_id == events[0].event_id
    assert events[0].aggregate_type == "owner_migration_session"
    assert events[0].payload_summary_json == {
        "count": 2,
        "batch_id": aggregate_id,
        "operator": "pytest",
        "source": "owner_migration",
    }
    assert "wm_owner_a" not in str(events[0].payload_summary_json)
    assert run_total == 4
    assert sorted(run.consumer_name for run in runs) == [
        "ai_assist_notify_consumer",
        "customer_owner_projection_consumer",
        "customer_summary_mark_dirty_consumer",
        "webhook_owner_migration_consumer",
    ]
