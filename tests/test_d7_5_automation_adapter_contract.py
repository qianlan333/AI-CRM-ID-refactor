from __future__ import annotations

import importlib
from pathlib import Path

from aicrm_next.automation_engine.application import (
    ApplyActivationWebhookCommand,
    EnqueueWorkflowRunCommand,
    GenerateAgentOutputCommand,
    OverrideFollowupTypeCommand,
    PushMemberContextToOpenClawCommand,
    RunAgentTaskCommand,
    RunWorkflowNodeCommand,
)
from aicrm_next.automation_engine.dto import ActivationWebhookRequest, OverrideFollowupTypeRequest, PushOpenClawContextRequest
from aicrm_next.automation_engine.repo import InMemoryAutomationRepository
from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
from aicrm_next.integration_gateway.automation_adapters import (
    AutomationActivationGateway,
    AutomationAgentRuntimeAdapter,
    AutomationWorkflowRuntimeAdapter,
    AutomationWriteGateway,
    OpenClawWebhookAdapter,
)
from aicrm_next.integration_gateway.idempotency import reset_idempotency_store

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_d7_5_files_exist() -> None:
    for relpath in [
        "aicrm_next/integration_gateway/automation_contracts.py",
        "aicrm_next/integration_gateway/automation_adapters.py",
        "docs/d7_5_automation_openclaw_runtime_adapter_contract.md",
        "docs/d7_5_automation_adapter_implementation_report.md",
        "tools/check_d7_5_automation_adapter_contract.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists(), relpath


def test_adapter_contract_classes_and_methods_exist() -> None:
    contracts = importlib.import_module("aicrm_next.integration_gateway.automation_contracts")
    adapters = importlib.import_module("aicrm_next.integration_gateway.automation_adapters")
    required = {
        "AutomationWriteGateway": ["override_followup_type", "confirm_conversion", "enter_silent", "exit_marketing", "build_write_preview", "record_write_audit"],
        "AutomationActivationGateway": ["receive_activation_event", "normalize_activation_payload", "build_activation_preview", "record_activation_audit"],
        "OpenClawWebhookAdapter": ["push_member_context", "push_workflow_context", "build_openclaw_payload_preview", "record_openclaw_audit"],
        "AutomationWorkflowRuntimeAdapter": ["enqueue_workflow_run", "run_workflow_node", "run_due_workflows", "build_workflow_runtime_preview", "record_workflow_runtime_audit"],
        "AutomationAgentRuntimeAdapter": ["run_agent_task", "generate_agent_output", "review_agent_output", "build_agent_runtime_preview", "record_agent_runtime_audit"],
    }
    for class_name, methods in required.items():
        assert hasattr(contracts, f"{class_name}Contract")
        cls = getattr(adapters, class_name)
        for method in methods:
            assert callable(getattr(cls, method))


def _assert_result_shape(result: dict) -> None:
    assert {
        "ok",
        "adapter",
        "mode",
        "operation",
        "idempotency_key",
        "target",
        "result",
        "audit_id",
        "side_effect_executed",
        "error_code",
        "error_message",
    } <= set(result)
    assert result["side_effect_executed"] is False


def test_fake_adapter_operations_are_deterministic_with_idempotency_key() -> None:
    reset_audit_events()
    reset_idempotency_store()
    first = AutomationWriteGateway("fake").override_followup_type(
        member_id="member_002",
        external_userid="wx_ext_002",
        followup_type="priority",
        idempotency_key="same-key",
    )
    second = AutomationWriteGateway("fake").override_followup_type(
        member_id="member_002",
        external_userid="wx_ext_002",
        followup_type="priority",
        idempotency_key="same-key",
    )
    _assert_result_shape(first)
    assert first["result"] == second["result"]
    assert first["result"]["real_automation_write_executed"] is False


def test_fake_write_activation_openclaw_workflow_agent_return_stable_fake_results() -> None:
    reset_audit_events()
    reset_idempotency_store()
    results = [
        AutomationWriteGateway("fake").confirm_conversion(member_id="member_002"),
        AutomationActivationGateway("fake").receive_activation_event(activation_event_id="act_001", mobile="13800138001"),
        OpenClawWebhookAdapter("fake").push_member_context(member_id="member_002", external_userid="wx_ext_002"),
        AutomationWorkflowRuntimeAdapter("fake").enqueue_workflow_run(workflow_id="workflow_001", member_id="member_002"),
        AutomationAgentRuntimeAdapter("fake").run_agent_task(agent_task_id="agent_task_001", member_id="member_002"),
    ]
    for result in results:
        _assert_result_shape(result)
        assert result["ok"] is True
        assert result["mode"] == "fake"
    assert results[0]["result"]["real_automation_write_executed"] is False
    assert results[1]["result"]["real_activation_webhook_executed"] is False
    assert results[2]["result"]["real_openclaw_push_executed"] is False
    assert results[2]["result"]["real_external_webhook_executed"] is False
    assert results[3]["result"]["real_workflow_runtime_executed"] is False
    assert results[4]["result"]["real_agent_runtime_executed"] is False


def test_disabled_and_production_modes_fail_closed(monkeypatch) -> None:
    disabled = AutomationWriteGateway("disabled").confirm_conversion(member_id="member_002")
    assert disabled["ok"] is False
    assert disabled["error_code"] == "adapter_disabled"
    assert disabled["side_effect_executed"] is False

    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_AUTOMATION_WRITES", raising=False)
    guarded = AutomationWriteGateway("production").confirm_conversion(member_id="member_002")
    assert guarded["ok"] is False
    assert guarded["error_code"] == "production_guard_failed"
    assert guarded["side_effect_executed"] is False

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_AUTOMATION_WRITES", "true")
    still_closed = AutomationWriteGateway("production").confirm_conversion(member_id="member_002")
    assert still_closed["ok"] is False
    assert still_closed["error_code"] == "production_not_implemented"
    assert still_closed["side_effect_executed"] is False


def test_staging_mode_has_no_side_effects() -> None:
    result = OpenClawWebhookAdapter("staging").push_workflow_context(workflow_id="workflow_001", member_id="member_002")
    assert result["ok"] is True
    assert result["mode"] == "staging"
    assert result["side_effect_executed"] is False
    assert result["result"]["real_openclaw_push_executed"] is False


def test_audit_record_created_for_each_adapter_family() -> None:
    reset_audit_events()
    reset_idempotency_store()
    AutomationWriteGateway("fake").confirm_conversion(member_id="member_002")
    AutomationActivationGateway("fake").receive_activation_event(mobile="13800138001")
    OpenClawWebhookAdapter("fake").push_member_context(member_id="member_002")
    AutomationWorkflowRuntimeAdapter("fake").enqueue_workflow_run(workflow_id="workflow_001")
    AutomationAgentRuntimeAdapter("fake").run_agent_task(agent_task_id="agent_task_001")
    events = list_audit_events()
    adapters = {event["adapter"] for event in events}
    assert {
        "AutomationWriteGateway",
        "AutomationActivationGateway",
        "OpenClawWebhookAdapter",
        "AutomationWorkflowRuntimeAdapter",
        "AutomationAgentRuntimeAdapter",
    } <= adapters
    assert all(event["side_effect_executed"] is False for event in events)


class SpyWriteGateway(AutomationWriteGateway):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def override_followup_type(self, **kwargs):
        self.calls.append("override_followup_type")
        return super().override_followup_type(**kwargs)


class SpyActivationGateway(AutomationActivationGateway):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def receive_activation_event(self, **kwargs):
        self.calls.append("receive_activation_event")
        return super().receive_activation_event(**kwargs)


class SpyOpenClawAdapter(OpenClawWebhookAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def push_member_context(self, **kwargs):
        self.calls.append("push_member_context")
        return super().push_member_context(**kwargs)


class SpyWorkflowRuntimeAdapter(AutomationWorkflowRuntimeAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def enqueue_workflow_run(self, **kwargs):
        self.calls.append("enqueue_workflow_run")
        return super().enqueue_workflow_run(**kwargs)

    def run_workflow_node(self, **kwargs):
        self.calls.append("run_workflow_node")
        return super().run_workflow_node(**kwargs)


class SpyAgentRuntimeAdapter(AutomationAgentRuntimeAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def run_agent_task(self, **kwargs):
        self.calls.append("run_agent_task")
        return super().run_agent_task(**kwargs)

    def generate_agent_output(self, **kwargs):
        self.calls.append("generate_agent_output")
        return super().generate_agent_output(**kwargs)


def test_automation_application_uses_write_activation_openclaw_boundaries() -> None:
    repo = InMemoryAutomationRepository()
    write = SpyWriteGateway()
    activation = SpyActivationGateway()
    openclaw = SpyOpenClawAdapter()
    override = OverrideFollowupTypeCommand(repo=repo, write_gateway=write)(
        "member_002",
        OverrideFollowupTypeRequest(followup_type="priority", operator="qa"),
    )
    activation_result = ApplyActivationWebhookCommand(repo=repo, activation_gateway=activation)(
        ActivationWebhookRequest(mobile="13800138001", source="fixture_audit")
    )
    openclaw_result = PushMemberContextToOpenClawCommand(repo=repo, openclaw_adapter=openclaw)("member_002", PushOpenClawContextRequest())
    assert write.calls == ["override_followup_type"]
    assert activation.calls == ["receive_activation_event"]
    assert openclaw.calls == ["push_member_context"]
    assert override["adapter_contract"]["automation_write"]["adapter"] == "AutomationWriteGateway"
    assert activation_result["adapter_contract"]["activation"]["adapter"] == "AutomationActivationGateway"
    assert openclaw_result["adapter_contract"]["openclaw"]["adapter"] == "OpenClawWebhookAdapter"
    assert not any(override["side_effect_safety"].values())
    assert not any(activation_result["side_effect_safety"].values())
    assert not any(openclaw_result["side_effect_safety"].values())


def test_workflow_and_agent_commands_use_runtime_boundaries() -> None:
    workflow = SpyWorkflowRuntimeAdapter()
    agent = SpyAgentRuntimeAdapter()
    enqueue = EnqueueWorkflowRunCommand(workflow_runtime_adapter=workflow)(workflow_id="workflow_001", member_id="member_002")
    node = RunWorkflowNodeCommand(workflow_runtime_adapter=workflow)(workflow_id="workflow_001", node_id="node_001", member_id="member_002")
    run = RunAgentTaskCommand(agent_runtime_adapter=agent)(agent_task_id="agent_task_001", member_id="member_002")
    output = GenerateAgentOutputCommand(agent_runtime_adapter=agent)(agent_task_id="agent_task_001", member_id="member_002")
    assert workflow.calls == ["enqueue_workflow_run", "run_workflow_node"]
    assert agent.calls == ["run_agent_task", "generate_agent_output"]
    assert enqueue["adapter_contract"]["workflow_runtime"]["adapter"] == "AutomationWorkflowRuntimeAdapter"
    assert node["adapter_contract"]["workflow_runtime"]["side_effect_executed"] is False
    assert run["adapter_contract"]["agent_runtime"]["adapter"] == "AutomationAgentRuntimeAdapter"
    assert output["adapter_contract"]["agent_runtime"]["side_effect_executed"] is False


def test_automation_smoke_and_parity_tools_pass() -> None:
    smoke_tool = importlib.import_module("tools.automation_readonly_gray_smoke")
    parity_tool = importlib.import_module("tools.compare_automation_conversion_parity")
    smoke = smoke_tool.run_smoke(type("Args", (), {"next_testclient": True, "next_base_url": ""})())
    parity = parity_tool.run_compare(
        type(
            "Args",
            (),
            {
                "old_fixture_dir": str(PROJECT_ROOT / "tests/fixtures/old_automation_conversion"),
                "old_base_url": "",
                "next_testclient": True,
                "next_base_url": "",
            },
        )()
    )
    assert smoke["ok"] is True
    assert parity["ok"] is True
    assert smoke["side_effect_safety"]["real_openclaw_push_executed"] is False
    assert parity["side_effect_safety"]["old_write_endpoints_executed"] is False


def test_d7_5_checker_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d7_5_automation_adapter_contract")
    report = checker.run_check()
    assert report["ok"] is True, report["blockers"]
    assert report["automation_smoke"]["ok"] is True
    assert report["automation_parity"]["ok"] is True


def test_docs_do_not_mark_production_or_delete_ready() -> None:
    for relpath in [
        "docs/d7_5_automation_openclaw_runtime_adapter_contract.md",
        "docs/d7_5_automation_adapter_implementation_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = (PROJECT_ROOT / relpath).read_text(encoding="utf-8")
        assert "production_ready" not in text
        assert "production_approved" not in text
        assert "delete_ready" not in text


def test_no_old_backend_imports_in_aicrm_next() -> None:
    offenders: list[Path] = []
    for path in (PROJECT_ROOT / "aicrm_next").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "wecom_ability_service" in text or "openclaw_service" in text:
            offenders.append(path.relative_to(PROJECT_ROOT))
    assert offenders == []
