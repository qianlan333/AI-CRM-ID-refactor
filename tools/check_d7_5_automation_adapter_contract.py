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
    "aicrm_next/integration_gateway/automation_contracts.py",
    "aicrm_next/integration_gateway/automation_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
    "aicrm_next/automation_engine/application.py",
    "tools/automation_readonly_gray_smoke.py",
    "tools/compare_automation_conversion_parity.py",
    "tests/fixtures/old_automation_conversion/overview.default.json",
]

DOCS_TO_SCAN = [
    "docs/d7_5_automation_openclaw_runtime_adapter_contract.md",
    "docs/d7_5_automation_adapter_implementation_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]

FORBIDDEN_STATUS_MARKERS = ["production_ready", "production_approved", "delete_ready"]

REQUIRED_METHODS: dict[str, list[str]] = {
    "AutomationWriteGateway": [
        "override_followup_type",
        "confirm_conversion",
        "enter_silent",
        "exit_marketing",
        "build_write_preview",
        "record_write_audit",
    ],
    "AutomationActivationGateway": [
        "receive_activation_event",
        "normalize_activation_payload",
        "build_activation_preview",
        "record_activation_audit",
    ],
    "OpenClawWebhookAdapter": [
        "push_member_context",
        "push_workflow_context",
        "build_openclaw_payload_preview",
        "record_openclaw_audit",
    ],
    "AutomationWorkflowRuntimeAdapter": [
        "enqueue_workflow_run",
        "run_workflow_node",
        "run_due_workflows",
        "build_workflow_runtime_preview",
        "record_workflow_runtime_audit",
    ],
    "AutomationAgentRuntimeAdapter": [
        "run_agent_task",
        "generate_agent_output",
        "review_agent_output",
        "build_agent_runtime_preview",
        "record_agent_runtime_audit",
    ],
}

PRODUCTION_FLAGS = {
    "AutomationWriteGateway": "AICRM_NEXT_ENABLE_REAL_AUTOMATION_WRITES",
    "AutomationActivationGateway": "AICRM_NEXT_ENABLE_REAL_AUTOMATION_ACTIVATION",
    "OpenClawWebhookAdapter": "AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK",
    "AutomationWorkflowRuntimeAdapter": "AICRM_NEXT_ENABLE_REAL_AUTOMATION_WORKFLOW_RUNTIME",
    "AutomationAgentRuntimeAdapter": "AICRM_NEXT_ENABLE_REAL_AUTOMATION_AGENT_RUNTIME",
}


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


def _sample_call(instance: Any) -> Json:
    name = instance.__class__.__name__
    if name == "AutomationWriteGateway":
        return instance.override_followup_type(member_id="member_002", external_userid="wx_ext_002", followup_type="priority")
    if name == "AutomationActivationGateway":
        return instance.receive_activation_event(activation_event_id="activation_fixture_001", external_userid="wx_ext_002", mobile="13800138001")
    if name == "OpenClawWebhookAdapter":
        return instance.push_member_context(member_id="member_002", external_userid="wx_ext_002", payload_summary={"source": "checker"})
    if name == "AutomationWorkflowRuntimeAdapter":
        return instance.enqueue_workflow_run(workflow_id="workflow_fixture_001", member_id="member_002")
    if name == "AutomationAgentRuntimeAdapter":
        return instance.run_agent_task(agent_task_id="agent_task_fixture_001", member_id="member_002")
    raise AssertionError(f"unknown adapter {name}")


def _check_adapter_contracts(blockers: list[Json]) -> Json:
    module = importlib.import_module("aicrm_next.integration_gateway.automation_adapters")
    contracts: Json = {}
    for class_name, methods in REQUIRED_METHODS.items():
        cls = getattr(module, class_name, None)
        missing = [method for method in methods if cls is None or not callable(getattr(cls, method, None))]
        contracts[class_name] = {"exists": cls is not None, "missing_methods": missing}
        if cls is None:
            blockers.append({"reason": "missing_adapter_class", "class": class_name})
        for method in missing:
            blockers.append({"reason": "missing_adapter_method", "class": class_name, "method": method})
    return contracts


def _check_modes(blockers: list[Json]) -> Json:
    module = importlib.import_module("aicrm_next.integration_gateway.automation_adapters")
    mode_env_names = [
        "AICRM_NEXT_AUTOMATION_WRITE_MODE",
        "AICRM_NEXT_AUTOMATION_ACTIVATION_MODE",
        "AICRM_NEXT_OPENCLAW_WEBHOOK_MODE",
        "AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME_MODE",
        "AICRM_NEXT_AUTOMATION_AGENT_RUNTIME_MODE",
    ]
    saved = {name: os.environ.get(name) for name in mode_env_names + list(PRODUCTION_FLAGS.values())}
    for name in mode_env_names + list(PRODUCTION_FLAGS.values()):
        os.environ.pop(name, None)
    try:
        defaults = {
            "automation_write": module.build_automation_write_gateway().mode,
            "automation_activation": module.build_automation_activation_gateway().mode,
            "openclaw_webhook": module.build_openclaw_webhook_adapter().mode,
            "automation_workflow_runtime": module.build_automation_workflow_runtime_adapter().mode,
            "automation_agent_runtime": module.build_automation_agent_runtime_adapter().mode,
        }
        if any(mode != "fake" for mode in defaults.values()):
            blockers.append({"reason": "default_mode_not_fake", "defaults": defaults})

        guards: Json = {"defaults": defaults, "production_without_flag": {}, "production_with_flag": {}, "disabled": {}}
        for class_name, flag in PRODUCTION_FLAGS.items():
            cls = getattr(module, class_name)
            disabled_result = _sample_call(cls("disabled"))
            guards["disabled"][class_name] = disabled_result["error_code"]
            if disabled_result["error_code"] != "adapter_disabled":
                blockers.append({"reason": "disabled_mode_not_stable", "class": class_name, "error_code": disabled_result["error_code"]})
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
        return guards
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _check_idempotency_audit_side_effects(blockers: list[Json]) -> tuple[Json, Json, Json]:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.automation_adapters import (
        AutomationActivationGateway,
        AutomationAgentRuntimeAdapter,
        AutomationWorkflowRuntimeAdapter,
        AutomationWriteGateway,
        OpenClawWebhookAdapter,
    )
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store

    reset_audit_events()
    reset_idempotency_store()
    adapters = [
        AutomationWriteGateway("fake"),
        AutomationActivationGateway("fake"),
        OpenClawWebhookAdapter("fake"),
        AutomationWorkflowRuntimeAdapter("fake"),
        AutomationAgentRuntimeAdapter("fake"),
    ]
    results = [_sample_call(adapter) for adapter in adapters]
    repeated = AutomationWriteGateway("fake").confirm_conversion(member_id="member_002", idempotency_key="d7_5_repeat_key")
    repeated_again = AutomationWriteGateway("fake").confirm_conversion(member_id="member_002", idempotency_key="d7_5_repeat_key")
    required_fields = {
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
    }
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
        smoke_tool = importlib.import_module("tools.automation_readonly_gray_smoke")
        smoke = smoke_tool.run_smoke(Namespace(next_testclient=True, next_base_url="", output_md="", output_json=""))
    except Exception as exc:
        smoke = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "automation_smoke_failed", "error": smoke["error"]})
    try:
        parity_tool = importlib.import_module("tools.compare_automation_conversion_parity")
        parity = parity_tool.run_compare(
            Namespace(
                old_fixture_dir=str(_path("tests/fixtures/old_automation_conversion")),
                old_base_url="",
                next_testclient=True,
                next_base_url="",
                output_md="",
                output_json="",
            )
        )
    except Exception as exc:
        parity = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "automation_parity_failed", "error": parity["error"]})
    if not smoke.get("ok"):
        blockers.append({"reason": "automation_smoke_not_ok"})
    if not parity.get("ok"):
        blockers.append({"reason": "automation_parity_not_ok"})
    if smoke.get("ok") and parity.get("ok"):
        warnings.append({"reason": "automation_smoke_and_parity_fixture_mode", "message": "Automation smoke/parity ran in fake fixture/TestClient mode only."})
    return smoke, parity


def _check_source_guards(blockers: list[Json]) -> Json:
    source = _read("aicrm_next/integration_gateway/automation_adapters.py")
    app_source = _read("aicrm_next/automation_engine/application.py")
    flags_present = {flag: flag in source for flag in PRODUCTION_FLAGS.values()}
    boundary_present = {
        "automation_write": "build_automation_write_gateway" in app_source,
        "automation_activation": "build_automation_activation_gateway" in app_source,
        "openclaw": "build_openclaw_webhook_adapter" in app_source,
        "workflow_runtime": "build_automation_workflow_runtime_adapter" in app_source,
        "agent_runtime": "build_automation_agent_runtime_adapter" in app_source,
    }
    if not all(flags_present.values()):
        blockers.append({"reason": "missing_production_guard_flag", "flags": flags_present})
    if not all(boundary_present.values()):
        blockers.append({"reason": "automation_application_boundary_missing", "boundary_present": boundary_present})
    return {"flags_present": flags_present, "application_boundary_present": boundary_present}


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_files = [{"path": relpath} for relpath in CONTRACT_FILES if not _path(relpath).exists()]
    for item in missing_files:
        blockers.append({"reason": "missing_required_file", "path": item["path"]})
    adapter_contracts = _check_adapter_contracts(blockers)
    mode_guards = _check_modes(blockers)
    idempotency, audit, side_effect_safety = _check_idempotency_audit_side_effects(blockers)
    missing_docs, forbidden_status_markers = _check_docs(blockers)
    source_guards = _check_source_guards(blockers)
    automation_smoke, automation_parity = _check_smoke_parity(blockers, warnings)
    recommendation = (
        "D7.5 Automation adapter contract is fake-contract ready; proceed to D7.5 validation review before any later runtime or OpenClaw production work."
        if not blockers
        else "Do not proceed; resolve D7.5 Automation adapter contract blockers first."
    )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "adapter_contracts": adapter_contracts,
        "mode_guards": {**mode_guards, **source_guards},
        "idempotency": idempotency,
        "audit": audit,
        "side_effect_safety": side_effect_safety,
        "automation_smoke": {"ok": bool(automation_smoke.get("ok")), "summary": automation_smoke.get("mode") or automation_smoke.get("error")},
        "automation_parity": {"ok": bool(automation_parity.get("ok")), "summary": automation_parity.get("mode") or automation_parity.get("error")},
        "missing_files": missing_files,
        "missing_docs": missing_docs,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": recommendation,
    }


def write_json_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# D7.5 Automation Adapter Contract Check",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- blockers: {len(report['blockers'])}",
        f"- warnings: {len(report['warnings'])}",
        f"- automation_smoke: {'PASS' if report['automation_smoke']['ok'] else 'FAIL'}",
        f"- automation_parity: {'PASS' if report['automation_parity']['ok'] else 'FAIL'}",
        f"- recommendation: {report['recommendation']}",
        "",
        "## Adapter Contracts",
        "",
        "| adapter | exists | missing_methods |",
        "| --- | --- | --- |",
    ]
    for adapter, item in report["adapter_contracts"].items():
        lines.append(f"| {adapter} | {str(item['exists']).lower()} | {', '.join(item['missing_methods']) or '-'} |")
    if report["blockers"]:
        lines.extend(["", "## Blockers", ""])
        for blocker in report["blockers"]:
            lines.append(f"- `{blocker.get('reason')}`: {json.dumps(blocker, ensure_ascii=False, sort_keys=True)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check D7.5 Automation write/OpenClaw/runtime adapter contract.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_check()
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
