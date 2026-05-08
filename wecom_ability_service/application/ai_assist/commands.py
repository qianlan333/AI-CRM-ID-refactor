from __future__ import annotations

from typing import Any, Mapping

from ...domains.customer_pulse import service as customer_pulse_domain_service
from ...domains.customer_pulse.access import (
    assert_customer_pulse_feedback_permission,
    assert_customer_pulse_internal_job_access,
    assert_customer_pulse_page_visible,
    assert_customer_pulse_request_context,
)
from ...domains.followup_orchestrator import service as followup_orchestrator_domain_service
from .dto import (
    ApplyFollowupMissionActionCommandDTO,
    AssignFollowupMissionCommandDTO,
    AssignFollowupMissionResultDTO,
    CustomerPulseActionExecuteResultDTO,
    CustomerPulseActionPreviewResultDTO,
    CustomerPulseActionUndoResultDTO,
    CustomerPulseFeedbackResultDTO,
    CustomerPulseRecomputeEnqueueResultDTO,
    CustomerPulseRefreshResultDTO,
    CustomerPulseRunDueResultDTO,
    EnqueueCustomerPulseRecomputeCommandDTO,
    ExecuteCustomerActionCommandDTO,
    ExecuteCustomerActionResultDTO,
    ExecuteCustomerPulseCardActionCommandDTO,
    ExecuteFollowupMissionItemActionCommandDTO,
    FollowupMissionActionResultDTO,
    FollowupMissionItemExecuteResultDTO,
    FollowupMissionItemPreviewResultDTO,
    FollowupMissionItemUndoResultDTO,
    PreviewCustomerActionCommandDTO,
    PreviewCustomerActionResultDTO,
    PreviewCustomerPulseCardActionCommandDTO,
    PreviewFollowupMissionItemActionCommandDTO,
    RefreshCustomerPulseCardsCommandDTO,
    RunDueCustomerPulseSnapshotJobCommandDTO,
    SubmitCustomerPulseFeedbackCommandDTO,
    SyncFollowupMissionsCommandDTO,
    UndoCustomerActionCommandDTO,
    UndoCustomerActionResultDTO,
    UndoCustomerPulseCardActionCommandDTO,
    UndoFollowupMissionItemActionCommandDTO,
)


def _t(value: Any) -> str:
    return str(value or "").strip()


def _d(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return dict(value or {})


class RefreshCustomerPulseCardsCommand:
    def __call__(self, dto: RefreshCustomerPulseCardsCommandDTO) -> CustomerPulseRefreshResultDTO:
        access_context = assert_customer_pulse_page_visible(_d(dto.access_context))
        return customer_pulse_domain_service.refresh_customer_pulse_cards(
            external_userids=list(dto.external_userids or []),
            limit=int(dto.limit or 50),
            operator=_t(dto.operator),
            tenant_context=access_context,
            allowed_owner_userids=list(dto.allowed_owner_userids or []),
        )

    execute = __call__


class EnqueueCustomerPulseRecomputeCommand:
    def __call__(self, dto: EnqueueCustomerPulseRecomputeCommandDTO) -> CustomerPulseRecomputeEnqueueResultDTO:
        job_scope = assert_customer_pulse_internal_job_access(_d(dto.access_context))
        operator = _t(dto.operator)
        external_userids = [_t(item) for item in dto.external_userids if _t(item)]
        if _t(dto.external_userid):
            external_userids.insert(0, _t(dto.external_userid))
        external_userids = list(dict.fromkeys(external_userids))

        if len(external_userids) <= 1:
            return customer_pulse_domain_service.enqueue_customer_pulse_recompute(
                external_userid=(external_userids[0] if external_userids else ""),
                owner_userid=_t(dto.owner_userid),
                delay_seconds=int(dto.delay_seconds or 0),
                operator=operator,
                trigger_source=_t(dto.trigger_source),
                trigger_ref_type=_t(dto.trigger_ref_type),
                trigger_ref_id=_t(dto.trigger_ref_id),
                tenant_context=_d(job_scope.get("tenant_context")),
            )

        jobs = [
            customer_pulse_domain_service.enqueue_customer_pulse_recompute(
                external_userid=external_userid,
                owner_userid=_t(dto.owner_userid),
                delay_seconds=int(dto.delay_seconds or 0),
                operator=operator,
                trigger_source=_t(dto.trigger_source),
                trigger_ref_type=_t(dto.trigger_ref_type),
                trigger_ref_id=_t(dto.trigger_ref_id),
                tenant_context=_d(job_scope.get("tenant_context")),
            )
            for external_userid in external_userids
        ]
        return {"ok": True, "jobs": jobs, "count": len(jobs)}

    execute = __call__


class RunDueCustomerPulseSnapshotJobCommand:
    def __call__(self, dto: RunDueCustomerPulseSnapshotJobCommandDTO) -> CustomerPulseRunDueResultDTO:
        job_scope = assert_customer_pulse_internal_job_access(_d(dto.access_context))
        return customer_pulse_domain_service.run_due_customer_pulse_snapshot_job(
            limit=int(dto.limit or 50),
            rescan_limit=int(dto.rescan_limit or 20),
            operator=_t(dto.operator),
            tenant_context=_d(job_scope.get("tenant_context")),
            allowed_owner_userids=list(dto.allowed_owner_userids or job_scope.get("allowed_owner_userids") or []),
        )

    execute = __call__


class PreviewCustomerPulseCardActionCommand:
    def __call__(self, dto: PreviewCustomerPulseCardActionCommandDTO) -> CustomerPulseActionPreviewResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.preview_customer_pulse_card_action(
            int(dto.card_id),
            action_type=_t(dto.action_type),
            track_click=bool(dto.track_click),
            metric_source=_t(dto.metric_source),
            operator=_t(dto.operator),
            tenant_context=access_context,
        )

    execute = __call__


# alias commands that share the same logic via DTO type
class PreviewCustomerActionCommand:
    def __call__(self, dto: PreviewCustomerActionCommandDTO) -> PreviewCustomerActionResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.preview_customer_pulse_card_action(
            int(dto.card_id),
            action_type=_t(dto.action_type),
            track_click=bool(dto.track_click),
            metric_source=_t(dto.metric_source),
            operator=_t(dto.operator),
            tenant_context=access_context,
        )

    execute = __call__


class ExecuteCustomerPulseCardActionCommand:
    def __call__(self, dto: ExecuteCustomerPulseCardActionCommandDTO) -> CustomerPulseActionExecuteResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.execute_customer_pulse_card_action(
            int(dto.card_id),
            action_type=_t(dto.action_type),
            extra_payload=_d(dto.action_payload),
            operator=_t(dto.operator),
            tenant_context=access_context,
        )

    execute = __call__


class ExecuteCustomerActionCommand:
    def __call__(self, dto: ExecuteCustomerActionCommandDTO) -> ExecuteCustomerActionResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.execute_customer_pulse_card_action(
            int(dto.card_id),
            action_type=_t(dto.action_type),
            extra_payload=_d(dto.action_payload),
            operator=_t(dto.operator),
            tenant_context=access_context,
        )

    execute = __call__


class UndoCustomerPulseCardActionCommand:
    def __call__(self, dto: UndoCustomerPulseCardActionCommandDTO) -> CustomerPulseActionUndoResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.undo_customer_pulse_card_action_execution(
            int(dto.execution_id),
            operator=_t(dto.operator),
            tenant_context=access_context,
        )

    execute = __call__


class UndoCustomerActionCommand:
    def __call__(self, dto: UndoCustomerActionCommandDTO) -> UndoCustomerActionResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.undo_customer_pulse_card_action_execution(
            int(dto.execution_id),
            operator=_t(dto.operator),
            tenant_context=access_context,
        )

    execute = __call__


class SubmitCustomerPulseFeedbackCommand:
    def __call__(self, dto: SubmitCustomerPulseFeedbackCommandDTO) -> CustomerPulseFeedbackResultDTO:
        access_context = assert_customer_pulse_feedback_permission(_d(dto.access_context))
        payload = _d(dto.feedback_payload)
        return customer_pulse_domain_service.submit_customer_pulse_feedback(
            int(dto.card_id),
            feedback_type=_t(dto.feedback_type),
            operator=_t(dto.operator),
            note=_t(payload.get("note") or payload.get("comments") or payload.get("comment")),
            payload=payload,
            tenant_context=access_context,
        )

    execute = __call__


def _followup_inbox_context(access_context: Mapping[str, Any] | None) -> dict[str, Any]:
    from ...domains.customer_pulse.access import assert_customer_pulse_inbox_view

    return assert_customer_pulse_inbox_view(_d(access_context))


class SyncFollowupMissionsCommand:
    def __call__(self, dto: SyncFollowupMissionsCommandDTO) -> dict:
        access_context = _followup_inbox_context(dto.access_context)
        return followup_orchestrator_domain_service.sync_followup_orchestrator_missions(
            scope=_t(dto.scope) or "team",
            owner_userid=_t(dto.owner_userid),
            external_userid=_t(dto.external_userid),
            limit=int(dto.limit or 50),
            access_context=access_context,
        )

    execute = __call__


def _apply_followup_mission_action(dto: ApplyFollowupMissionActionCommandDTO) -> FollowupMissionActionResultDTO:
    access_context = _followup_inbox_context(dto.access_context)
    return followup_orchestrator_domain_service.apply_followup_orchestrator_mission_action(
        mission_key=_t(dto.mission_key),
        action_type=_t(dto.action_type),
        actor_userid=_t(dto.actor_userid),
        actor_role=_t(dto.actor_role),
        operator=_t(dto.operator),
        tenant_context=access_context,
        mission_item_key=_t(dto.mission_item_key),
        note=_t(dto.note),
    )


class ApplyFollowupMissionActionCommand:
    def __call__(self, dto: ApplyFollowupMissionActionCommandDTO) -> FollowupMissionActionResultDTO:
        return _apply_followup_mission_action(dto)

    execute = __call__


class AssignFollowupMissionCommand:
    def __call__(self, dto: AssignFollowupMissionCommandDTO) -> AssignFollowupMissionResultDTO:
        return _apply_followup_mission_action(dto)

    execute = __call__


class PreviewFollowupMissionItemActionCommand:
    def __call__(self, dto: PreviewFollowupMissionItemActionCommandDTO) -> FollowupMissionItemPreviewResultDTO:
        access_context = _followup_inbox_context(dto.access_context)
        return followup_orchestrator_domain_service.preview_followup_orchestrator_mission_item_action(
            mission_key=_t(dto.mission_key),
            mission_item_key=_t(dto.mission_item_key),
            action_type=_t(dto.action_type),
            actor_userid=_t(dto.actor_userid),
            operator=_t(dto.operator),
            access_context=access_context,
        )

    execute = __call__


class ExecuteFollowupMissionItemActionCommand:
    def __call__(self, dto: ExecuteFollowupMissionItemActionCommandDTO) -> FollowupMissionItemExecuteResultDTO:
        access_context = _followup_inbox_context(dto.access_context)
        return followup_orchestrator_domain_service.execute_followup_orchestrator_mission_item_action(
            mission_key=_t(dto.mission_key),
            mission_item_key=_t(dto.mission_item_key),
            action_type=_t(dto.action_type),
            actor_userid=_t(dto.actor_userid),
            actor_role=_t(dto.actor_role),
            operator=_t(dto.operator),
            note=_t(dto.note),
            extra_payload=_d(dto.action_payload),
            access_context=access_context,
        )

    execute = __call__


class UndoFollowupMissionItemActionCommand:
    def __call__(self, dto: UndoFollowupMissionItemActionCommandDTO) -> FollowupMissionItemUndoResultDTO:
        access_context = _followup_inbox_context(dto.access_context)
        return followup_orchestrator_domain_service.undo_followup_orchestrator_mission_item_action(
            mission_key=_t(dto.mission_key),
            mission_item_key=_t(dto.mission_item_key),
            execution_id=int(dto.execution_id or 0),
            actor_userid=_t(dto.actor_userid),
            actor_role=_t(dto.actor_role),
            operator=_t(dto.operator),
            access_context=access_context,
        )

    execute = __call__


__all__ = [
    "ApplyFollowupMissionActionCommand",
    "AssignFollowupMissionCommand",
    "EnqueueCustomerPulseRecomputeCommand",
    "ExecuteCustomerActionCommand",
    "ExecuteCustomerPulseCardActionCommand",
    "ExecuteFollowupMissionItemActionCommand",
    "PreviewCustomerActionCommand",
    "PreviewCustomerPulseCardActionCommand",
    "PreviewFollowupMissionItemActionCommand",
    "RefreshCustomerPulseCardsCommand",
    "RunDueCustomerPulseSnapshotJobCommand",
    "SubmitCustomerPulseFeedbackCommand",
    "SyncFollowupMissionsCommand",
    "UndoCustomerActionCommand",
    "UndoCustomerPulseCardActionCommand",
    "UndoFollowupMissionItemActionCommand",
]
