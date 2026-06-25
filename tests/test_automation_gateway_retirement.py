from __future__ import annotations

import aicrm_next.integration_gateway.automation_adapters as automation_adapters
import aicrm_next.integration_gateway.automation_contracts as automation_contracts


def test_retired_member_workflow_and_openclaw_gateways_are_not_exported() -> None:
    retired_names = {
        "AutomationWriteGateway",
        "build_automation_write_gateway",
        "OpenClawWebhookAdapter",
        "build_openclaw_webhook_adapter",
        "AutomationWorkflowRuntimeAdapter",
        "build_automation_workflow_runtime_adapter",
    }

    for name in retired_names:
        assert not hasattr(automation_adapters, name)

    assert not hasattr(automation_contracts, "AutomationWorkflowRuntimeAdapterContract")
    assert not hasattr(automation_contracts, "AutomationWriteGatewayContract")
    assert not hasattr(automation_contracts, "OpenClawWebhookAdapterContract")


def test_agent_runtime_gateway_remains_available() -> None:
    adapter = automation_adapters.build_automation_agent_runtime_adapter()

    result = adapter.generate_agent_output(
        agent_task_id="agent_task_fixture",
        member_id="member_fixture",
        payload_summary={"source": "pytest"},
        idempotency_key="pytest-agent-output",
    )

    assert result["ok"] is True
    assert result["adapter"] == "AutomationAgentRuntimeAdapter"
    assert result["operation"] == "generate_agent_output"
    assert result["result"]["generated"] is True
    assert result["result"]["real_agent_runtime_executed"] is False
