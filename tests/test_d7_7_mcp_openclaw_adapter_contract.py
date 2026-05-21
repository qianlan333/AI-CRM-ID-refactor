from __future__ import annotations

import importlib
from argparse import Namespace
from pathlib import Path

from aicrm_next.automation_engine.application import PushMemberContextToOpenClawCommand
from aicrm_next.automation_engine.dto import PushOpenClawContextRequest
from aicrm_next.automation_engine.repo import InMemoryAutomationRepository
from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
from aicrm_next.integration_gateway.dispatch import McpToolDispatcher
from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
from aicrm_next.integration_gateway.mcp_openclaw_adapters import (
    AutomationContextToolAdapter,
    CustomerContextToolAdapter,
    McpCompatibilityGateway,
    McpToolGateway,
    OpenClawLegacyBridgeAdapter,
    mcp_openclaw_side_effect_safety,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_d7_7_files_exist() -> None:
    for relpath in [
        "aicrm_next/integration_gateway/mcp_openclaw_contracts.py",
        "aicrm_next/integration_gateway/mcp_openclaw_adapters.py",
        "docs/d7_7_mcp_openclaw_legacy_adapter_contract.md",
        "docs/d7_7_mcp_openclaw_legacy_retirement_report.md",
        "tools/check_d7_7_mcp_openclaw_adapter_contract.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists(), relpath


def test_adapter_contract_classes_and_methods_exist() -> None:
    contracts = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_contracts")
    adapters = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_adapters")
    required = {
        "McpToolGateway": ["list_tools", "invoke_tool", "build_tool_preview", "validate_tool_request", "record_tool_audit"],
        "CustomerContextToolAdapter": ["resolve_customer", "get_customer_context", "get_customer_timeline", "get_recent_messages", "build_customer_context_preview", "record_customer_context_audit"],
        "AutomationContextToolAdapter": ["get_member_context", "get_pool_summary", "get_execution_records", "build_automation_context_preview", "record_automation_context_audit"],
        "OpenClawLegacyBridgeAdapter": ["build_openclaw_context_payload", "push_context_to_openclaw", "resolve_legacy_skill_request", "build_legacy_bridge_preview", "record_openclaw_bridge_audit"],
        "McpCompatibilityGateway": ["map_legacy_tool_name", "map_legacy_payload", "normalize_tool_response", "build_compatibility_preview", "record_compatibility_audit"],
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


def test_fake_operations_are_deterministic_with_idempotency_key() -> None:
    reset_audit_events()
    reset_idempotency_store()
    operations = [
        (McpToolGateway("fake"), lambda adapter, key: adapter.list_tools(idempotency_key=key)),
        (McpToolGateway("fake"), lambda adapter, key: adapter.invoke_tool(tool_name="get_customer_context", arguments={"external_userid": "wx_ext_001"}, idempotency_key=key)),
        (CustomerContextToolAdapter("fake"), lambda adapter, key: adapter.get_customer_context(external_userid="wx_ext_001", idempotency_key=key)),
        (CustomerContextToolAdapter("fake"), lambda adapter, key: adapter.get_recent_messages(external_userid="wx_ext_001", idempotency_key=key)),
        (AutomationContextToolAdapter("fake"), lambda adapter, key: adapter.get_member_context(member_id="member_002", idempotency_key=key)),
        (OpenClawLegacyBridgeAdapter("fake"), lambda adapter, key: adapter.push_context_to_openclaw(member_id="member_002", idempotency_key=key)),
        (McpCompatibilityGateway("fake"), lambda adapter, key: adapter.map_legacy_tool_name(tool_name="customer_context", idempotency_key=key)),
    ]
    for index, (adapter, call) in enumerate(operations):
        first = call(adapter, f"d7-7-same-key-{index}")
        second = call(adapter, f"d7-7-same-key-{index}")
        _assert_result_shape(first)
        assert first["result"] == second["result"]


def test_disabled_and_production_modes_fail_closed(monkeypatch) -> None:
    cases = [
        (McpToolGateway, "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS", lambda adapter: adapter.list_tools()),
        (CustomerContextToolAdapter, "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS", lambda adapter: adapter.get_customer_context(external_userid="wx_ext_001")),
        (AutomationContextToolAdapter, "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS", lambda adapter: adapter.get_member_context(member_id="member_002")),
        (OpenClawLegacyBridgeAdapter, "AICRM_NEXT_ENABLE_REAL_OPENCLAW_BRIDGE", lambda adapter: adapter.push_context_to_openclaw(member_id="member_002")),
        (McpCompatibilityGateway, "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS", lambda adapter: adapter.map_legacy_tool_name(tool_name="customer_context")),
    ]
    for cls, flag, call in cases:
        disabled = call(cls("disabled"))
        assert disabled["ok"] is False
        assert disabled["error_code"] == "adapter_disabled"
        assert disabled["side_effect_executed"] is False

        monkeypatch.delenv(flag, raising=False)
        guarded = call(cls("production"))
        assert guarded["ok"] is False
        assert guarded["error_code"] == "production_guard_failed"
        assert guarded["side_effect_executed"] is False

        monkeypatch.setenv(flag, "true")
        still_closed = call(cls("production"))
        assert still_closed["ok"] is False
        assert still_closed["error_code"] == "production_not_implemented"
        assert still_closed["side_effect_executed"] is False
        monkeypatch.delenv(flag, raising=False)


def test_staging_mode_has_no_side_effects() -> None:
    results = [
        McpToolGateway("staging").list_tools(),
        CustomerContextToolAdapter("staging").get_recent_messages(external_userid="wx_ext_001"),
        AutomationContextToolAdapter("staging").get_member_context(member_id="member_002"),
        OpenClawLegacyBridgeAdapter("staging").build_legacy_bridge_preview(skill_name="customer_context"),
        McpCompatibilityGateway("staging").map_legacy_tool_name(tool_name="customer_context"),
    ]
    for result in results:
        assert result["ok"] is True
        assert result["mode"] == "staging"
        assert result["side_effect_executed"] is False
        assert not any(result["result"]["side_effect_safety"].values())


def test_audit_record_created_for_each_adapter_family() -> None:
    reset_audit_events()
    reset_idempotency_store()
    McpToolGateway("fake").list_tools()
    CustomerContextToolAdapter("fake").get_customer_context(external_userid="wx_ext_001")
    AutomationContextToolAdapter("fake").get_member_context(member_id="member_002")
    OpenClawLegacyBridgeAdapter("fake").push_context_to_openclaw(member_id="member_002")
    McpCompatibilityGateway("fake").map_legacy_tool_name(tool_name="customer_context")
    events = list_audit_events()
    adapters = {event["adapter"] for event in events}
    assert {"McpToolGateway", "CustomerContextToolAdapter", "AutomationContextToolAdapter", "OpenClawLegacyBridgeAdapter", "McpCompatibilityGateway"} <= adapters
    assert all(event["side_effect_executed"] is False for event in events)
    assert all({"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event) for event in events)


def test_mcp_customer_recent_and_automation_context_paths_use_boundaries() -> None:
    dispatcher = McpToolDispatcher()
    customer = dispatcher.dispatch("get_customer_context", {"external_userid": "wx_ext_001", "request_id": "req_001"})
    recent = dispatcher.dispatch("get_recent_messages", {"external_userid": "wx_ext_001", "limit": 2, "request_id": "req_002"})
    automation = dispatcher.dispatch("get_automation_context", {"member_id": "member_002", "request_id": "req_003"})

    assert customer["adapter_contract"]["customer_context_tool"]["adapter"] == "CustomerContextToolAdapter"
    assert recent["adapter_contract"]["customer_context_tool"]["operation"] == "get_recent_messages"
    assert automation["adapter_contract"]["automation_context_tool"]["adapter"] == "AutomationContextToolAdapter"
    assert customer["adapter_contract"]["mcp_tool"]["adapter"] == "McpToolGateway"
    assert recent["messages"]
    assert automation["member"]["member_id"] == "member_002"
    assert not any(mcp_openclaw_side_effect_safety().values())


class SpyOpenClawLegacyBridgeAdapter(OpenClawLegacyBridgeAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def push_context_to_openclaw(self, **kwargs):
        self.calls.append("push_context_to_openclaw")
        return super().push_context_to_openclaw(**kwargs)


def test_openclaw_fake_push_uses_legacy_bridge_boundary() -> None:
    bridge = SpyOpenClawLegacyBridgeAdapter()
    repo = InMemoryAutomationRepository()
    result = PushMemberContextToOpenClawCommand(repo=repo, legacy_bridge_adapter=bridge)("member_002", PushOpenClawContextRequest())
    assert bridge.calls == ["push_context_to_openclaw"]
    assert result["adapter_contract"]["openclaw_legacy_bridge"]["adapter"] == "OpenClawLegacyBridgeAdapter"
    assert result["side_effect_safety"]["real_openclaw_push_executed"] is False


def test_customer_and_automation_smoke_parity_remain_pass() -> None:
    customer_smoke = importlib.import_module("tools.customer_read_model_gray_smoke")
    assert customer_smoke.run_smoke(Namespace(old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))["ok"] is True
    customer_parity = importlib.import_module("tools.compare_customer_read_model_parity")
    assert customer_parity.run_compare(Namespace(old_fixture_dir=str(PROJECT_ROOT / "experiments/ai_crm_next/tests/fixtures/old_customer_read_model"), old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))["ok"] is True
    automation_smoke = importlib.import_module("tools.automation_readonly_gray_smoke")
    assert automation_smoke.run_smoke(Namespace(old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))["ok"] is True
    automation_parity = importlib.import_module("tools.compare_automation_conversion_parity")
    assert automation_parity.run_compare(Namespace(old_fixture_dir=str(PROJECT_ROOT / "tests/fixtures/old_automation_conversion"), old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))["ok"] is True


def test_openclaw_service_still_exists_and_docs_are_not_mislabelled() -> None:
    assert (PROJECT_ROOT / "openclaw_service").exists()
    docs = [
        "docs/d7_7_mcp_openclaw_legacy_adapter_contract.md",
        "docs/d7_7_mcp_openclaw_legacy_retirement_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_retirement_plan.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]
    for relpath in docs:
        text = (PROJECT_ROOT / relpath).read_text(encoding="utf-8")
        assert "production_ready" not in text
        assert "production_approved" not in text
        assert "delete_ready" not in text


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (PROJECT_ROOT / "aicrm_next").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in text
        assert "openclaw_service" not in text
