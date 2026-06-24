from __future__ import annotations

import aicrm_next.automation_engine.application as automation_application
from aicrm_next.automation_engine.customer_webhooks import (
    ApplyCustomerActivationWebhookCommand,
    execute_customer_webhook_command,
    reset_customer_webhook_fixture_state,
)


def test_automation_application_surface_is_next_native() -> None:
    assert ApplyCustomerActivationWebhookCommand


def test_retired_task_workflow_member_action_surface_is_not_exported() -> None:
    retired_names = {
        "ListTasksQuery",
        "CreateTaskCommand",
        "GetTaskDetailQuery",
        "UpdateTaskCommand",
        "ListWorkflowsQuery",
        "CreateWorkflowCommand",
        "ListWorkflowNodesQuery",
        "CreateWorkflowNodeCommand",
        "ListAutomationMembersQuery",
        "GetAutomationMemberDetailQuery",
        "OverrideFollowupTypeCommand",
        "ConfirmConversionCommand",
        "EnterSilentPoolCommand",
        "ExitMarketingCommand",
        "PushMemberContextToOpenClawCommand",
        "RunDueWorkflowsCommand",
        "GenerateAgentOutputCommand",
        "ReviewAgentOutputCommand",
        "ApplyQuestionnaireResultCommand",
        "ApplyActivationFactCommand",
        "ApplyActivationWebhookCommand",
    }

    for name in retired_names:
        assert not hasattr(automation_application, name)


def test_activation_webhook_command_plans_local_projection_without_external_call() -> None:
    reset_customer_webhook_fixture_state()

    result = execute_customer_webhook_command(
        ApplyCustomerActivationWebhookCommand(
            mobile="13800138000",
            activated_at="2026-05-01T00:00:00+00:00",
            source="pytest",
            source_route="/api/customer-automation/activation-webhook",
        )
    )

    assert result["ok"] is True
    assert result["source_status"] == "next_customer_activation_webhook"
    assert result["route_owner"] == "ai_crm_next"
    assert result["fallback_used"] is False
    assert result["real_external_call_executed"] is False
    assert result["side_effect_plan"]["adapter_mode"] == "local"


def test_retired_automation_member_write_dtos_and_repo_methods_are_not_exported() -> None:
    import aicrm_next.automation_engine.dto as automation_dto
    import aicrm_next.automation_engine.repo as automation_repo

    for name in (
        "ApplyQuestionnaireResultRequest",
        "ApplyTrialOpenedFactRequest",
        "ApplyActivationFactRequest",
        "OverrideFollowupTypeRequest",
        "AutomationActionRequest",
        "PushOpenClawContextRequest",
    ):
        assert not hasattr(automation_dto, name)

    source = automation_repo.__loader__.get_source(automation_repo.__name__) or ""
    for marker in (
        "def save_member(",
        "def create_member_from_questionnaire(",
        "def create_execution_record(",
    ):
        assert marker not in source
