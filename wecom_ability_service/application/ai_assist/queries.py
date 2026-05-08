from __future__ import annotations

from typing import Any, Mapping

from ...customer_center.pulse_service import build_customer_pulse
from ...domains.customer_pulse import service as customer_pulse_domain_service
from ...domains.customer_pulse.access import (
    assert_customer_pulse_evidence_view,
    assert_customer_pulse_inbox_view,
    assert_customer_pulse_page_visible,
    assert_customer_pulse_request_context,
    assert_customer_pulse_widget_view,
    customer_pulse_permission_summary,
    customer_pulse_template_access_payload,
    resolve_customer_pulse_read_scope,
)
from ...domains.followup_orchestrator import service as followup_orchestrator_domain_service
from .dto import (
    CustomerPulseCardEvidenceQueryDTO,
    CustomerPulseCardEvidenceResultDTO,
    CustomerPulseCardQueryDTO,
    CustomerPulseCardResultDTO,
    CustomerPulseCustomerDetailQueryDTO,
    CustomerPulseCustomerDetailResultDTO,
    CustomerPulseDetailQueryDTO,
    CustomerPulseDetailResultDTO,
    CustomerPulseFeatureGateQueryDTO,
    CustomerPulseFeatureGateResultDTO,
    CustomerPulseInboxQueryDTO,
    CustomerPulseInboxResultDTO,
    CustomerPulseMetricsQueryDTO,
    CustomerPulseMetricsResultDTO,
    CustomerPulseStatsQueryDTO,
    CustomerPulseStatsResultDTO,
    FollowupCandidatesQueryDTO,
    FollowupCandidatesResultDTO,
    FollowupCustomerQueryDTO,
    FollowupCustomerResultDTO,
    FollowupFeatureGateQueryDTO,
    FollowupFeatureGateResultDTO,
    FollowupMissionBoardQueryDTO,
    FollowupMissionBoardResultDTO,
    FollowupMissionDetailQueryDTO,
    FollowupMissionDetailResultDTO,
    FollowupMyMissionsQueryDTO,
    FollowupMyMissionsResultDTO,
    FollowupOverviewQueryDTO,
    FollowupOverviewResultDTO,
    FollowupTeamBoardQueryDTO,
    FollowupTeamBoardResultDTO,
)


def _t(value: Any) -> str:
    return str(value or "").strip()


def _d(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return dict(value or {})


class GetCustomerPulseFeatureGateQuery:
    def __call__(
        self,
        dto: CustomerPulseFeatureGateQueryDTO | None = None,
    ) -> CustomerPulseFeatureGateResultDTO:
        dto = dto or CustomerPulseFeatureGateQueryDTO()
        access_context = _d(dto.access_context)
        assert_customer_pulse_request_context(access_context)
        return {
            "enabled": customer_pulse_domain_service.is_customer_pulse_inbox_enabled(access_context=access_context),
            "feature_gate": customer_pulse_domain_service.customer_pulse_feature_gate_summary(access_context=access_context),
            "permissions": customer_pulse_permission_summary(access_context),
            "template_access": customer_pulse_template_access_payload(access_context),
        }

    execute = __call__


def _list_customer_pulse_inbox(dto: CustomerPulseInboxQueryDTO) -> CustomerPulseInboxResultDTO:
    access_context = assert_customer_pulse_inbox_view(_d(dto.access_context))
    filters = _d(dto.filters)
    filters.setdefault("limit", 50)
    return customer_pulse_domain_service.build_customer_pulse_inbox_payload(
        **filters,
        tenant_context=access_context,
        metric_source=_t(dto.metric_source) or "admin_customer_pulse_api",
    )


class ListCustomerPulseInboxQuery:
    def __call__(self, dto: CustomerPulseInboxQueryDTO) -> CustomerPulseInboxResultDTO:
        return _list_customer_pulse_inbox(dto)

    execute = __call__


class GetCustomerPulseInboxQuery:
    def __call__(self, dto: CustomerPulseInboxQueryDTO) -> CustomerPulseInboxResultDTO:
        return _list_customer_pulse_inbox(dto)

    execute = __call__


def _get_customer_pulse_stats(dto) -> dict[str, Any]:
    access_context = assert_customer_pulse_page_visible(_d(dto.access_context))
    return customer_pulse_domain_service.build_customer_pulse_ops_dashboard_payload(
        days=int(dto.days or 7),
        tenant_context=access_context,
        owner_userids=list(dto.owner_userids or []),
    )


class GetCustomerPulseStatsQuery:
    def __call__(self, dto: CustomerPulseStatsQueryDTO) -> CustomerPulseStatsResultDTO:
        return _get_customer_pulse_stats(dto)

    execute = __call__


class GetCustomerPulseMetricsQuery:
    def __call__(self, dto: CustomerPulseMetricsQueryDTO) -> CustomerPulseMetricsResultDTO:
        return _get_customer_pulse_stats(dto)

    execute = __call__


class GetCustomerPulseDetailQuery:
    def __call__(self, dto: CustomerPulseDetailQueryDTO) -> CustomerPulseDetailResultDTO:
        external_userid = _t(dto.external_userid)
        if not external_userid:
            raise LookupError("customer not found")

        access_context = _d(dto.access_context)
        assert_customer_pulse_request_context(access_context)

        if not customer_pulse_domain_service.is_customer_pulse_inbox_enabled(access_context=access_context):
            return {
                "external_userid": external_userid,
                "pulse": build_customer_pulse(external_userid),
                "customer_pulse": customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
                    external_userid,
                    tenant_context=access_context,
                ),
            }

        assert_customer_pulse_widget_view(access_context)
        read_scope = resolve_customer_pulse_read_scope(access_context=access_context)
        customer_pulse = customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
            external_userid,
            track_metrics=True,
            metric_source="customer_profile_widget_api",
            tenant_context=read_scope.get("tenant_context"),
            tenant_key=_t(read_scope.get("tenant_key")),
            allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
        )
        if customer_pulse.get("enabled") and not customer_pulse.get("card"):
            customer_pulse_domain_service.refresh_customer_pulse_cards(
                limit=1,
                operator=_t(read_scope.get("operator")) or "customer_profile_page",
                external_userids=[external_userid],
                tenant_context=read_scope.get("tenant_context"),
                tenant_key=_t(read_scope.get("tenant_key")),
                allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
            )
            customer_pulse = customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
                external_userid,
                track_metrics=True,
                metric_source="customer_profile_widget_api",
                tenant_context=read_scope.get("tenant_context"),
                tenant_key=_t(read_scope.get("tenant_key")),
                allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
            )

        return {
            "external_userid": external_userid,
            "pulse": build_customer_pulse(external_userid),
            "customer_pulse": customer_pulse,
        }

    execute = __call__


class GetCustomerPulseCustomerDetailQuery:
    def __call__(self, dto: CustomerPulseCustomerDetailQueryDTO) -> CustomerPulseCustomerDetailResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
            _t(dto.external_userid),
            track_metrics=bool(dto.track_metrics),
            tenant_context=access_context,
            tenant_key=_t(dto.tenant_key),
            allowed_owner_userids=list(dto.allowed_owner_userids or []),
        )

    execute = __call__


class GetCustomerPulseCardQuery:
    def __call__(self, dto: CustomerPulseCardQueryDTO) -> CustomerPulseCardResultDTO:
        access_context = assert_customer_pulse_request_context(_d(dto.access_context))
        return customer_pulse_domain_service.get_customer_pulse_card_payload(
            int(dto.card_id),
            tenant_context=access_context,
        )

    execute = __call__


class GetCustomerPulseCardEvidenceQuery:
    def __call__(self, dto: CustomerPulseCardEvidenceQueryDTO) -> CustomerPulseCardEvidenceResultDTO:
        access_context = assert_customer_pulse_evidence_view(_d(dto.access_context))
        return customer_pulse_domain_service.get_customer_pulse_card_evidence_payload(
            int(dto.card_id),
            tenant_context=access_context,
        )

    execute = __call__


class GetFollowupOrchestratorFeatureGateQuery:
    def __call__(
        self,
        dto: FollowupFeatureGateQueryDTO | None = None,
    ) -> FollowupFeatureGateResultDTO:
        dto = dto or FollowupFeatureGateQueryDTO()
        access_context = _d(dto.access_context)
        assert_customer_pulse_request_context(access_context)
        return {
            "enabled": followup_orchestrator_domain_service.is_followup_orchestrator_enabled(access_context=access_context),
            "feature_gate": followup_orchestrator_domain_service.followup_orchestrator_feature_gate_summary(access_context=access_context),
            "permissions": customer_pulse_permission_summary(access_context),
            "template_access": customer_pulse_template_access_payload(access_context),
        }

    execute = __call__


def _get_followup_overview(dto) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_d(dto.access_context))
    return followup_orchestrator_domain_service.build_followup_orchestrator_overview_payload(
        scope=_t(dto.scope) or "team",
        owner_userid=_t(dto.owner_userid),
        external_userid=_t(dto.external_userid),
        limit=int(dto.limit or 50),
        auto_sync=bool(dto.auto_sync),
        access_context=access_context,
    )


class GetFollowupOrchestratorOverviewQuery:
    def __call__(self, dto: FollowupOverviewQueryDTO) -> FollowupOverviewResultDTO:
        return _get_followup_overview(dto)

    execute = __call__


class ListFollowupCandidatesQuery:
    def __call__(self, dto: FollowupCandidatesQueryDTO) -> FollowupCandidatesResultDTO:
        return _get_followup_overview(dto)

    execute = __call__


class GetFollowupOrchestratorCustomerQuery:
    def __call__(self, dto: FollowupCustomerQueryDTO) -> FollowupCustomerResultDTO:
        access_context = assert_customer_pulse_inbox_view(_d(dto.access_context))
        return followup_orchestrator_domain_service.build_followup_orchestrator_customer_payload(
            external_userid=_t(dto.external_userid),
            access_context=access_context,
        )

    execute = __call__


class ListFollowupMyMissionsQuery:
    def __call__(self, dto: FollowupMyMissionsQueryDTO) -> FollowupMyMissionsResultDTO:
        access_context = assert_customer_pulse_inbox_view(_d(dto.access_context))
        return followup_orchestrator_domain_service.build_followup_orchestrator_my_missions_payload(
            actor_userid=_t(dto.actor_userid),
            limit=int(dto.limit or 50),
            auto_sync=bool(dto.auto_sync),
            access_context=access_context,
        )

    execute = __call__


def _get_followup_team_board(dto) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_d(dto.access_context))
    return followup_orchestrator_domain_service.build_followup_orchestrator_team_board_payload(
        limit=int(dto.limit or 50),
        auto_sync=bool(dto.auto_sync),
        access_context=access_context,
    )


class GetFollowupTeamBoardQuery:
    def __call__(self, dto: FollowupTeamBoardQueryDTO) -> FollowupTeamBoardResultDTO:
        return _get_followup_team_board(dto)

    execute = __call__


class GetFollowupMissionBoardQuery:
    def __call__(self, dto: FollowupMissionBoardQueryDTO) -> FollowupMissionBoardResultDTO:
        return _get_followup_team_board(dto)

    execute = __call__


class GetFollowupMissionDetailQuery:
    def __call__(self, dto: FollowupMissionDetailQueryDTO) -> FollowupMissionDetailResultDTO:
        access_context = assert_customer_pulse_inbox_view(_d(dto.access_context))
        return followup_orchestrator_domain_service.get_followup_orchestrator_mission_detail_payload(
            mission_key=_t(dto.mission_key),
            access_context=access_context,
            tenant_key=_t(dto.tenant_key),
        )

    execute = __call__


from .commands import (  # noqa: E402
    ApplyFollowupMissionActionCommand,
    EnqueueCustomerPulseRecomputeCommand,
    ExecuteCustomerPulseCardActionCommand,
    ExecuteFollowupMissionItemActionCommand,
    PreviewCustomerPulseCardActionCommand,
    PreviewFollowupMissionItemActionCommand,
    RefreshCustomerPulseCardsCommand,
    RunDueCustomerPulseSnapshotJobCommand,
    SubmitCustomerPulseFeedbackCommand,
    SyncFollowupMissionsCommand,
    UndoCustomerPulseCardActionCommand,
    UndoFollowupMissionItemActionCommand,
)


__all__ = [
    "ApplyFollowupMissionActionCommand",
    "EnqueueCustomerPulseRecomputeCommand",
    "ExecuteCustomerPulseCardActionCommand",
    "ExecuteFollowupMissionItemActionCommand",
    "GetCustomerPulseCardEvidenceQuery",
    "GetCustomerPulseCardQuery",
    "GetCustomerPulseCustomerDetailQuery",
    "GetCustomerPulseDetailQuery",
    "GetCustomerPulseFeatureGateQuery",
    "GetCustomerPulseInboxQuery",
    "GetCustomerPulseMetricsQuery",
    "GetCustomerPulseStatsQuery",
    "GetFollowupMissionBoardQuery",
    "GetFollowupMissionDetailQuery",
    "GetFollowupOrchestratorCustomerQuery",
    "GetFollowupOrchestratorFeatureGateQuery",
    "GetFollowupOrchestratorOverviewQuery",
    "GetFollowupTeamBoardQuery",
    "ListCustomerPulseInboxQuery",
    "ListFollowupCandidatesQuery",
    "ListFollowupMyMissionsQuery",
    "PreviewCustomerPulseCardActionCommand",
    "PreviewFollowupMissionItemActionCommand",
    "RefreshCustomerPulseCardsCommand",
    "RunDueCustomerPulseSnapshotJobCommand",
    "SubmitCustomerPulseFeedbackCommand",
    "SyncFollowupMissionsCommand",
    "UndoCustomerPulseCardActionCommand",
    "UndoFollowupMissionItemActionCommand",
]
