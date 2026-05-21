#!/usr/bin/env python
from __future__ import annotations

import argparse
import importlib
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from tools.d7_contract_check_common import (
    Json,
    check_adapter_methods,
    check_adapter_mode_guards,
    check_fake_operation_result_safety,
    clean_environment,
    collect_missing_files,
    ensure_project_root_on_path,
    project_path,
    read_project_text,
    resolve_project_root,
    scan_docs_for_forbidden_markers,
    write_json_report,
    write_markdown_lines,
)

PROJECT_ROOT = resolve_project_root(__file__)
ensure_project_root_on_path(PROJECT_ROOT)

CONTRACT_FILES = [
    "aicrm_next/integration_gateway/mcp_openclaw_contracts.py",
    "aicrm_next/integration_gateway/mcp_openclaw_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
    "aicrm_next/integration_gateway/dispatch.py",
    "aicrm_next/integration_gateway/mcp.py",
    "aicrm_next/customer_read_model/application.py",
    "aicrm_next/automation_engine/application.py",
    "tools/customer_read_model_gray_smoke.py",
    "tools/automation_readonly_gray_smoke.py",
    "tools/compare_customer_read_model_parity.py",
    "tools/compare_automation_conversion_parity.py",
]

DOCS_TO_SCAN = [
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

FORBIDDEN_STATUS_MARKERS = ["production_ready", "production_approved", "delete_ready"]

REQUIRED_METHODS: dict[str, list[str]] = {
    "McpToolGateway": ["list_tools", "invoke_tool", "build_tool_preview", "validate_tool_request", "record_tool_audit"],
    "CustomerContextToolAdapter": ["resolve_customer", "get_customer_context", "get_customer_timeline", "get_recent_messages", "build_customer_context_preview", "record_customer_context_audit"],
    "AutomationContextToolAdapter": ["get_member_context", "get_pool_summary", "get_execution_records", "build_automation_context_preview", "record_automation_context_audit"],
    "OpenClawLegacyBridgeAdapter": ["build_openclaw_context_payload", "push_context_to_openclaw", "resolve_legacy_skill_request", "build_legacy_bridge_preview", "record_openclaw_bridge_audit"],
    "McpCompatibilityGateway": ["map_legacy_tool_name", "map_legacy_payload", "normalize_tool_response", "build_compatibility_preview", "record_compatibility_audit"],
}

PRODUCTION_FLAGS = {
    "McpToolGateway": "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS",
    "CustomerContextToolAdapter": "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS",
    "AutomationContextToolAdapter": "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS",
    "OpenClawLegacyBridgeAdapter": "AICRM_NEXT_ENABLE_REAL_OPENCLAW_BRIDGE",
    "McpCompatibilityGateway": "AICRM_NEXT_ENABLE_REAL_MCP_TOOLS",
}


def _path(relpath: str) -> Path:
    return project_path(PROJECT_ROOT, relpath)


def _read(relpath: str) -> str:
    return read_project_text(PROJECT_ROOT, relpath)


def _sample_call(instance: Any) -> Json:
    name = instance.__class__.__name__
    if name == "McpToolGateway":
        return instance.list_tools(request_id="d7_7_check")
    if name == "CustomerContextToolAdapter":
        return instance.get_customer_context(external_userid="wx_ext_001", request_id="d7_7_check")
    if name == "AutomationContextToolAdapter":
        return instance.get_member_context(member_id="member_002", request_id="d7_7_check")
    if name == "OpenClawLegacyBridgeAdapter":
        return instance.push_context_to_openclaw(member_id="member_002", openclaw_context_id="d7_7_check")
    if name == "McpCompatibilityGateway":
        return instance.map_legacy_tool_name(tool_name="customer_context", request_id="d7_7_check")
    raise AssertionError(f"unknown adapter {name}")


def _check_required_files(blockers: list[Json]) -> list[Json]:
    return collect_missing_files(PROJECT_ROOT, CONTRACT_FILES, blockers, reason="missing_contract_file")


def _check_adapter_contracts(blockers: list[Json]) -> Json:
    contracts = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_contracts")
    adapters = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_adapters")
    return check_adapter_methods(adapters, REQUIRED_METHODS, blockers, contracts_module=contracts)


def _check_modes(blockers: list[Json]) -> Json:
    module = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_adapters")
    mode_env_names = [
        "AICRM_NEXT_MCP_TOOL_MODE",
        "AICRM_NEXT_OPENCLAW_LEGACY_MODE",
        "AICRM_NEXT_CUSTOMER_CONTEXT_TOOL_MODE",
        "AICRM_NEXT_AUTOMATION_CONTEXT_TOOL_MODE",
    ]
    real_flags = ["AICRM_NEXT_ENABLE_REAL_MCP_TOOLS", "AICRM_NEXT_ENABLE_REAL_OPENCLAW_BRIDGE", "AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK"]
    with clean_environment(mode_env_names + real_flags):
        defaults = {
            "mcp_tool": module.build_mcp_tool_gateway().mode,
            "openclaw_legacy": module.build_openclaw_legacy_bridge_adapter().mode,
            "customer_context_tool": module.build_customer_context_tool_adapter().mode,
            "automation_context_tool": module.build_automation_context_tool_adapter().mode,
            "mcp_compatibility": module.build_mcp_compatibility_gateway().mode,
        }
        if any(mode != "fake" for mode in defaults.values()):
            blockers.append({"reason": "default_mode_not_fake", "defaults": defaults})
        guards = check_adapter_mode_guards(module, PRODUCTION_FLAGS, _sample_call, blockers, defaults)
        source = _read("aicrm_next/integration_gateway/mcp_openclaw_adapters.py")
        guards["flags_present"] = {flag: flag in source for flag in real_flags}
        for flag, present in guards["flags_present"].items():
            if not present:
                blockers.append({"reason": "missing_production_guard_flag", "flag": flag})
        dispatch_source = _read("aicrm_next/integration_gateway/dispatch.py")
        app_source = _read("aicrm_next/automation_engine/application.py")
        guards["application_boundary_present"] = {
            "mcp_tool": "build_mcp_tool_gateway" in dispatch_source,
            "customer_context": "build_customer_context_tool_adapter" in dispatch_source,
            "automation_context": "build_automation_context_tool_adapter" in dispatch_source,
            "mcp_compatibility": "build_mcp_compatibility_gateway" in dispatch_source,
            "openclaw_legacy_bridge": "build_openclaw_legacy_bridge_adapter" in app_source,
        }
        for name, present in guards["application_boundary_present"].items():
            if not present:
                blockers.append({"reason": "application_boundary_missing", "boundary": name})
        return guards


def _check_idempotency_audit_side_effects(blockers: list[Json]) -> tuple[Json, Json, Json]:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.mcp_openclaw_adapters import (
        AutomationContextToolAdapter,
        CustomerContextToolAdapter,
        McpCompatibilityGateway,
        McpToolGateway,
        OpenClawLegacyBridgeAdapter,
    )

    reset_audit_events()
    reset_idempotency_store()
    adapters = [
        McpToolGateway("fake"),
        CustomerContextToolAdapter("fake"),
        AutomationContextToolAdapter("fake"),
        OpenClawLegacyBridgeAdapter("fake"),
        McpCompatibilityGateway("fake"),
    ]
    results = [_sample_call(adapter) for adapter in adapters]
    repeated = McpToolGateway("fake").invoke_tool(tool_name="get_customer_context", arguments={"external_userid": "wx_ext_001"}, idempotency_key="d7_7_repeat_key")
    repeated_again = McpToolGateway("fake").invoke_tool(tool_name="get_customer_context", arguments={"external_userid": "wx_ext_001"}, idempotency_key="d7_7_repeat_key")
    events = list_audit_events()
    return check_fake_operation_result_safety(results, repeated, repeated_again, events, blockers)


def _check_docs(blockers: list[Json]) -> tuple[list[Json], list[Json]]:
    return scan_docs_for_forbidden_markers(PROJECT_ROOT, DOCS_TO_SCAN, FORBIDDEN_STATUS_MARKERS, blockers)


def _check_smoke_parity(blockers: list[Json], warnings: list[Json]) -> tuple[Json, Json]:
    try:
        customer_smoke_tool = importlib.import_module("tools.customer_read_model_gray_smoke")
        customer_smoke = customer_smoke_tool.run_smoke(Namespace(old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))
    except Exception as exc:
        customer_smoke = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "customer_context_smoke_failed", "error": customer_smoke["error"]})
    try:
        automation_smoke_tool = importlib.import_module("tools.automation_readonly_gray_smoke")
        automation_smoke = automation_smoke_tool.run_smoke(Namespace(old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))
    except Exception as exc:
        automation_smoke = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "automation_context_smoke_failed", "error": automation_smoke["error"]})
    try:
        customer_parity_tool = importlib.import_module("tools.compare_customer_read_model_parity")
        customer_parity = customer_parity_tool.run_compare(Namespace(old_fixture_dir=str(_path("experiments/ai_crm_next/tests/fixtures/old_customer_read_model")), old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))
    except Exception as exc:
        customer_parity = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "customer_context_parity_failed", "error": customer_parity["error"]})
    try:
        automation_parity_tool = importlib.import_module("tools.compare_automation_conversion_parity")
        automation_parity = automation_parity_tool.run_compare(Namespace(old_fixture_dir=str(_path("tests/fixtures/old_automation_conversion")), old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))
    except Exception as exc:
        automation_parity = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "automation_context_parity_failed", "error": automation_parity["error"]})
    if not customer_smoke.get("ok"):
        blockers.append({"reason": "customer_context_smoke_not_ok"})
    if not automation_smoke.get("ok"):
        blockers.append({"reason": "automation_context_smoke_not_ok"})
    if not customer_parity.get("ok"):
        blockers.append({"reason": "customer_context_parity_not_ok"})
    if not automation_parity.get("ok"):
        blockers.append({"reason": "automation_context_parity_not_ok"})
    if customer_smoke.get("ok") and automation_smoke.get("ok") and customer_parity.get("ok") and automation_parity.get("ok"):
        warnings.append({"reason": "context_smoke_and_parity_fixture_mode", "message": "Customer and Automation context smoke/parity ran in fake fixture/TestClient mode only."})
    return {
        "customer_smoke": {"ok": bool(customer_smoke.get("ok")), "mode": customer_smoke.get("mode")},
        "customer_parity": {"ok": bool(customer_parity.get("ok")), "mode": customer_parity.get("mode")},
    }, {
        "automation_smoke": {"ok": bool(automation_smoke.get("ok")), "mode": automation_smoke.get("mode")},
        "automation_parity": {"ok": bool(automation_parity.get("ok")), "mode": automation_parity.get("mode")},
    }


def _check_openclaw_service_gate(blockers: list[Json]) -> Json:
    exists = _path("openclaw_service").exists()
    if not exists:
        blockers.append({"reason": "openclaw_service_missing"})
    legacy_delete = _read("docs/legacy_delete_batches.md")
    d7_report = _read("docs/d7_7_mcp_openclaw_legacy_retirement_report.md") if _path("docs/d7_7_mcp_openclaw_legacy_retirement_report.md").exists() else ""
    gate = {
        "openclaw_service_exists": exists,
        "not_delete_ready_wording": "not delete-ready" in legacy_delete or "not delete-ready" in d7_report,
        "physical_delete_not_requested": True,
    }
    if not gate["not_delete_ready_wording"]:
        blockers.append({"reason": "openclaw_service_gate_missing"})
    return gate


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_contract_files = _check_required_files(blockers)
    adapter_contracts = _check_adapter_contracts(blockers)
    mode_guards = _check_modes(blockers)
    idempotency, audit, side_effect_safety = _check_idempotency_audit_side_effects(blockers)
    missing_docs, forbidden_status_markers = _check_docs(blockers)
    customer_context_smoke, automation_context_smoke = _check_smoke_parity(blockers, warnings)
    openclaw_service_retirement_gate = _check_openclaw_service_gate(blockers)
    result: Json = {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "missing_contract_files": missing_contract_files,
        "adapter_contracts": adapter_contracts,
        "mode_guards": mode_guards,
        "idempotency": idempotency,
        "audit": audit,
        "side_effect_safety": side_effect_safety,
        "customer_context_smoke": customer_context_smoke,
        "automation_context_smoke": automation_context_smoke,
        "openclaw_service_retirement_gate": openclaw_service_retirement_gate,
        "missing_docs": missing_docs,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": (
            "D7.7 MCP/OpenClaw legacy adapter contract is fake-contract ready; proceed to D7.7 validation review before any OpenClaw, MCP external service, webhook, or physical legacy deletion work."
            if not blockers
            else "Fix D7.7 blockers before validation."
        ),
    }
    return result


def _write_markdown(path: str, result: Json) -> None:
    lines = [
        "# D7.7 MCP / OpenClaw Adapter Contract Check",
        "",
        f"- ok: `{str(result['ok']).lower()}`",
        f"- blockers: `{len(result['blockers'])}`",
        f"- warnings: `{len(result['warnings'])}`",
        f"- recommendation: {result['recommendation']}",
        "",
        "## Adapter Contracts",
    ]
    for name, item in result["adapter_contracts"].items():
        lines.append(f"- {name}: exists={item['exists']}, contract_exists={item['contract_exists']}, missing_methods={item['missing_methods']}")
    write_markdown_lines(Path(path), lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D7.7 MCP/OpenClaw legacy adapter contract.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    result = run_check()
    if args.output_md:
        _write_markdown(args.output_md, result)
        print(f"wrote markdown report: {args.output_md}")
    if args.output_json:
        write_json_report(result, Path(args.output_json), sort_keys=True)
        print(f"wrote json report: {args.output_json}")
    print(f"overall: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
