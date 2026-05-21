#!/usr/bin/env python
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

Json = dict[str, Any]

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
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


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
    missing = []
    for relpath in CONTRACT_FILES:
        if not _path(relpath).exists():
            missing.append({"path": relpath})
            blockers.append({"reason": "missing_contract_file", "path": relpath})
    return missing


def _check_adapter_contracts(blockers: list[Json]) -> Json:
    contracts = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_contracts")
    adapters = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_adapters")
    result: Json = {}
    for class_name, methods in REQUIRED_METHODS.items():
        contract_exists = hasattr(contracts, f"{class_name}Contract")
        cls = getattr(adapters, class_name, None)
        missing = [method for method in methods if cls is None or not callable(getattr(cls, method, None))]
        result[class_name] = {"exists": cls is not None, "contract_exists": contract_exists, "missing_methods": missing}
        if not contract_exists:
            blockers.append({"reason": "missing_adapter_contract", "class": class_name})
        if cls is None:
            blockers.append({"reason": "missing_adapter_class", "class": class_name})
        for method in missing:
            blockers.append({"reason": "missing_adapter_method", "class": class_name, "method": method})
    return result


def _check_modes(blockers: list[Json]) -> Json:
    module = importlib.import_module("aicrm_next.integration_gateway.mcp_openclaw_adapters")
    mode_env_names = [
        "AICRM_NEXT_MCP_TOOL_MODE",
        "AICRM_NEXT_OPENCLAW_LEGACY_MODE",
        "AICRM_NEXT_CUSTOMER_CONTEXT_TOOL_MODE",
        "AICRM_NEXT_AUTOMATION_CONTEXT_TOOL_MODE",
    ]
    real_flags = ["AICRM_NEXT_ENABLE_REAL_MCP_TOOLS", "AICRM_NEXT_ENABLE_REAL_OPENCLAW_BRIDGE", "AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK"]
    saved = {name: os.environ.get(name) for name in mode_env_names + real_flags}
    for name in mode_env_names + real_flags:
        os.environ.pop(name, None)
    try:
        defaults = {
            "mcp_tool": module.build_mcp_tool_gateway().mode,
            "openclaw_legacy": module.build_openclaw_legacy_bridge_adapter().mode,
            "customer_context_tool": module.build_customer_context_tool_adapter().mode,
            "automation_context_tool": module.build_automation_context_tool_adapter().mode,
            "mcp_compatibility": module.build_mcp_compatibility_gateway().mode,
        }
        if any(mode != "fake" for mode in defaults.values()):
            blockers.append({"reason": "default_mode_not_fake", "defaults": defaults})
        guards: Json = {"defaults": defaults, "production_without_flag": {}, "production_with_flag": {}, "disabled": {}}
        for class_name, flag in PRODUCTION_FLAGS.items():
            cls = getattr(module, class_name)
            disabled = _sample_call(cls("disabled"))
            guards["disabled"][class_name] = disabled["error_code"]
            if disabled["error_code"] != "adapter_disabled":
                blockers.append({"reason": "disabled_mode_not_stable", "class": class_name, "error_code": disabled["error_code"]})
            os.environ.pop(flag, None)
            guarded = _sample_call(cls("production"))
            guards["production_without_flag"][class_name] = guarded["error_code"]
            if guarded["error_code"] != "production_guard_failed":
                blockers.append({"reason": "production_mode_not_guarded", "class": class_name, "error_code": guarded["error_code"]})
            os.environ[flag] = "true"
            not_implemented = _sample_call(cls("production"))
            guards["production_with_flag"][class_name] = not_implemented["error_code"]
            if not_implemented["error_code"] != "production_not_implemented":
                blockers.append({"reason": "production_mode_not_fail_closed", "class": class_name, "error_code": not_implemented["error_code"]})
            os.environ.pop(flag, None)
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
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


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
    required_fields = {"ok", "adapter", "mode", "operation", "idempotency_key", "target", "result", "audit_id", "side_effect_executed", "error_code", "error_message"}
    missing_fields = {item["adapter"]: sorted(required_fields - set(item)) for item in results if required_fields - set(item)}
    if missing_fields:
        blockers.append({"reason": "result_shape_missing_fields", "missing_fields": missing_fields})
    side_effects = {item["adapter"]: item["side_effect_executed"] for item in results}
    if any(side_effects.values()):
        blockers.append({"reason": "side_effect_executed_true", "side_effects": side_effects})
    deterministic = repeated["result"] == repeated_again["result"]
    if not deterministic:
        blockers.append({"reason": "idempotency_not_deterministic"})
    events = list_audit_events()
    audit_ok = len(events) >= len(results) and all(
        {"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event)
        for event in events
    )
    if not audit_ok:
        blockers.append({"reason": "audit_record_shape_invalid"})
    return {"deterministic_repeated_result": deterministic}, {"audit_records": len(events), "shape_ok": audit_ok}, {"side_effect_executed": side_effects}


def _check_docs(blockers: list[Json]) -> tuple[list[Json], list[Json]]:
    missing_docs: list[Json] = []
    forbidden: list[Json] = []
    for relpath in DOCS_TO_SCAN:
        path = _path(relpath)
        if not path.exists():
            missing_docs.append({"path": relpath})
            blockers.append({"reason": "missing_doc", "path": relpath})
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                forbidden.append({"path": relpath, "marker": marker})
                blockers.append({"reason": "forbidden_status_marker", "path": relpath, "marker": marker})
    return missing_docs, forbidden


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
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote json report: {args.output_json}")
    print(f"overall: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
