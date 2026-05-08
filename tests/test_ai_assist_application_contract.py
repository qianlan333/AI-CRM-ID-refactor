from __future__ import annotations

import ast
from pathlib import Path

from wecom_ability_service.application.ai_assist import (
    ApplyFollowupMissionActionCommand,
    ApplyFollowupMissionActionCommandDTO,
    AssignFollowupMissionCommand,
    AssignFollowupMissionCommandDTO,
    CustomerPulseCardEvidenceQueryDTO,
    CustomerPulseCardQueryDTO,
    CustomerPulseDetailQueryDTO,
    CustomerPulseFeatureGateQueryDTO,
    CustomerPulseInboxQueryDTO,
    CustomerPulseMetricsQueryDTO,
    CustomerPulseStatsQueryDTO,
    EnqueueCustomerPulseRecomputeCommand,
    EnqueueCustomerPulseRecomputeCommandDTO,
    ExecuteCustomerActionCommand,
    ExecuteCustomerActionCommandDTO,
    ExecuteCustomerPulseCardActionCommand,
    ExecuteCustomerPulseCardActionCommandDTO,
    ExecuteFollowupMissionItemActionCommand,
    ExecuteFollowupMissionItemActionCommandDTO,
    FollowupCandidatesQueryDTO,
    FollowupCustomerQueryDTO,
    FollowupFeatureGateQueryDTO,
    FollowupMissionBoardQueryDTO,
    FollowupMissionDetailQueryDTO,
    FollowupMyMissionsQueryDTO,
    FollowupOverviewQueryDTO,
    FollowupTeamBoardQueryDTO,
    GetCustomerPulseInboxQuery,
    GetCustomerPulseMetricsQuery,
    GetCustomerPulseCardEvidenceQuery,
    GetCustomerPulseCardQuery,
    GetCustomerPulseDetailQuery,
    GetCustomerPulseFeatureGateQuery,
    GetCustomerPulseStatsQuery,
    GetFollowupMissionBoardQuery,
    GetFollowupMissionDetailQuery,
    GetFollowupOrchestratorCustomerQuery,
    GetFollowupOrchestratorFeatureGateQuery,
    GetFollowupOrchestratorOverviewQuery,
    GetFollowupTeamBoardQuery,
    ListCustomerPulseInboxQuery,
    ListFollowupCandidatesQuery,
    ListFollowupMyMissionsQuery,
    PreviewCustomerActionCommand,
    PreviewCustomerActionCommandDTO,
    PreviewCustomerPulseCardActionCommand,
    PreviewCustomerPulseCardActionCommandDTO,
    PreviewFollowupMissionItemActionCommand,
    PreviewFollowupMissionItemActionCommandDTO,
    RefreshCustomerPulseCardsCommand,
    RefreshCustomerPulseCardsCommandDTO,
    RunDueCustomerPulseSnapshotJobCommand,
    RunDueCustomerPulseSnapshotJobCommandDTO,
    SubmitCustomerPulseFeedbackCommand,
    SubmitCustomerPulseFeedbackCommandDTO,
    SyncFollowupMissionsCommand,
    SyncFollowupMissionsCommandDTO,
    UndoCustomerActionCommand,
    UndoCustomerActionCommandDTO,
    UndoCustomerPulseCardActionCommand,
    UndoCustomerPulseCardActionCommandDTO,
    UndoFollowupMissionItemActionCommand,
    UndoFollowupMissionItemActionCommandDTO,
)
from wecom_ability_service.application.ai_assist import commands as ai_assist_commands
from wecom_ability_service.application.ai_assist import queries as ai_assist_queries


def test_ai_assist_application_api_is_importable():
    assert GetCustomerPulseFeatureGateQuery
    assert GetCustomerPulseInboxQuery
    assert ListCustomerPulseInboxQuery
    assert GetCustomerPulseMetricsQuery
    assert GetCustomerPulseStatsQuery
    assert GetCustomerPulseDetailQuery
    assert GetCustomerPulseCardQuery
    assert GetCustomerPulseCardEvidenceQuery
    assert RefreshCustomerPulseCardsCommand
    assert EnqueueCustomerPulseRecomputeCommand
    assert RunDueCustomerPulseSnapshotJobCommand
    assert PreviewCustomerActionCommand
    assert PreviewCustomerPulseCardActionCommand
    assert ExecuteCustomerActionCommand
    assert ExecuteCustomerPulseCardActionCommand
    assert UndoCustomerActionCommand
    assert UndoCustomerPulseCardActionCommand
    assert SubmitCustomerPulseFeedbackCommand
    assert GetFollowupOrchestratorFeatureGateQuery
    assert GetFollowupOrchestratorOverviewQuery
    assert ListFollowupCandidatesQuery
    assert GetFollowupOrchestratorCustomerQuery
    assert ListFollowupMyMissionsQuery
    assert GetFollowupMissionBoardQuery
    assert GetFollowupTeamBoardQuery
    assert GetFollowupMissionDetailQuery
    assert SyncFollowupMissionsCommand
    assert AssignFollowupMissionCommand
    assert ApplyFollowupMissionActionCommand
    assert PreviewFollowupMissionItemActionCommand
    assert ExecuteFollowupMissionItemActionCommand
    assert UndoFollowupMissionItemActionCommand


