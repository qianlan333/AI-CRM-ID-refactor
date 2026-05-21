#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACT_FILES = [
    "aicrm_next/integration_gateway/user_ops_contracts.py",
    "aicrm_next/integration_gateway/user_ops_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
    "aicrm_next/ops_enrollment/application.py",
    "tools/user_ops_readonly_gray_smoke.py",
    "tools/compare_user_ops_parity.py",
    "experiments/ai_crm_next/tests/fixtures/old_user_ops/overview.default.json",
]
DOCS_TO_SCAN = [
    "docs/d7_3_user_ops_dnd_batch_send_wecom_dispatch_adapter_contract.md",
    "docs/d7_3_user_ops_adapter_implementation_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]
REQUIRED_METHODS = {
    "UserOpsDndWriteGateway": [
        "enable_do_not_disturb",
        "cancel_do_not_disturb",
        "build_dnd_preview",
        "record_dnd_audit",
    ],
    "UserOpsBatchSendGateway": [
        "build_batch_send_preview",
        "execute_batch_send",
        "create_send_record",
        "build_send_result_summary",
    ],
    "WeComMessageDispatchAdapter": [
        "send_private_message",
        "send_group_message",
        "send_moment",
        "build_dispatch_preview",
        "resolve_dispatch_target",
        "record_dispatch_audit",
    ],
    "UserOpsDeferredJobGateway": [
        "enqueue_deferred_job",
        "run_due_jobs",
        "build_deferred_job_preview",
        "record_deferred_job_audit",
    ],
}
REQUIRED_RESULT_FIELDS = [
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
]
FORBIDDEN_DOC_MARKERS = ["production_ready", "delete_ready"]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _class_methods(path: str, class_name: str) -> list[str]:
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [child.name for child in node.body if isinstance(child, ast.FunctionDef)]
    return []


def _check_runtime() -> dict[str, Any]:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.user_ops_adapters import (
        UserOpsBatchSendGateway,
        UserOpsDeferredJobGateway,
        UserOpsDndWriteGateway,
        WeComMessageDispatchAdapter,
    )

    reset_audit_events()
    reset_idempotency_store()
    dnd_a = UserOpsDndWriteGateway("fake").enable_do_not_disturb(external_userid="external_1", reason_code="manual")
    dnd_b = UserOpsDndWriteGateway("fake").enable_do_not_disturb(external_userid="external_1", reason_code="manual")
    batch_a = UserOpsBatchSendGateway("fake").build_batch_send_preview(
        selection_mode="manual",
        selected_ids=[1],
        content="hello",
        targets=[{"external_userid": "external_1"}],
        owner_buckets=[{"owner_userid": "owner_1", "target_count": 1, "external_userids": ["external_1"]}],
    )
    batch_b = UserOpsBatchSendGateway("fake").build_batch_send_preview(
        selection_mode="manual",
        selected_ids=[1],
        content="hello",
        targets=[{"external_userid": "external_1"}],
        owner_buckets=[{"owner_userid": "owner_1", "target_count": 1, "external_userids": ["external_1"]}],
    )
    execute = UserOpsBatchSendGateway("fake").execute_batch_send(
        content="hello",
        owner_buckets=[{"owner_userid": "owner_1", "target_count": 1, "external_userids": ["external_1"]}],
    )
    dispatch_private = WeComMessageDispatchAdapter("fake").send_private_message(external_userid="external_1", owner_userid="owner_1", content="hello")
    dispatch_group = WeComMessageDispatchAdapter("fake").send_group_message(group_chat_id="group_1", owner_userid="owner_1", content="hello")
    dispatch_moment = WeComMessageDispatchAdapter("fake").send_moment(owner_userid="owner_1", content="hello")
    deferred = UserOpsDeferredJobGateway("fake").run_due_jobs(now="2026-05-21T00:00:00Z", limit=10)
    disabled = UserOpsBatchSendGateway("disabled").execute_batch_send(content="hello")

    previous_env = os.environ.pop("AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH", None)
    try:
        guarded = WeComMessageDispatchAdapter("production").send_private_message(external_userid="external_1", content="hello")
    finally:
        if previous_env is not None:
            os.environ["AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH"] = previous_env

    os.environ["AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH"] = "true"
    try:
        guarded_enabled = WeComMessageDispatchAdapter("production").send_private_message(external_userid="external_1", content="hello")
    finally:
        os.environ.pop("AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH", None)
        if previous_env is not None:
            os.environ["AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH"] = previous_env

    checked_results = [
        dnd_a,
        dnd_b,
        batch_a,
        batch_b,
        execute,
        dispatch_private,
        dispatch_group,
        dispatch_moment,
        deferred,
        disabled,
        guarded,
        guarded_enabled,
    ]
    events = list_audit_events()
    return {
        "stable_shape": all(all(field in item for field in REQUIRED_RESULT_FIELDS) for item in checked_results),
        "fake_dnd_deterministic": dnd_a["result"] == dnd_b["result"],
        "fake_batch_preview_deterministic": batch_a["result"] == batch_b["result"],
        "fake_execute_no_dispatch": execute["result"].get("dispatched") is False,
        "fake_dispatch_no_send": all(item["result"].get("sent") is False for item in [dispatch_private, dispatch_group, dispatch_moment]),
        "fake_deferred_no_run": deferred["result"].get("executed") is False,
        "disabled_error": disabled["ok"] is False and disabled["error_code"] == "adapter_disabled",
        "production_guard": guarded["ok"] is False and guarded["error_code"] == "production_guard_failed",
        "production_enabled_not_implemented": guarded_enabled["ok"] is False and guarded_enabled["error_code"] == "production_not_implemented",
        "side_effect_executed_false": all(item["side_effect_executed"] is False for item in checked_results),
        "audit_events_created": len(events) >= len(checked_results) and all(event.get("audit_id") for event in events),
        "audit_fields_present": all(
            {"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event)
            for event in events
        ),
        "real_flags": {
            "real_dnd_write_executed": False,
            "real_batch_send_executed": False,
            "real_wecom_dispatch_executed": False,
            "real_deferred_jobs_executed": False,
            "real_wecom_media_upload_executed": False,
        },
    }


def _run_user_ops_smoke() -> dict[str, Any]:
    from tools import user_ops_readonly_gray_smoke as smoke

    report = smoke.run_smoke(
        Namespace(
            old_base_url="",
            next_testclient=True,
            next_base_url="",
            output_md="/tmp/unused.md",
            output_json="/tmp/unused.json",
        )
    )
    return {
        "ok": bool(report.get("ok")),
        "summary": report.get("summary", {}),
        "side_effect_safety": report.get("side_effect_safety", {}),
        "blockers": report.get("blockers", []),
    }


def _run_user_ops_parity() -> dict[str, Any]:
    from tools import compare_user_ops_parity as parity

    report = parity.run_compare(
        Namespace(
            old_base_url="",
            next_base_url="",
            old_fixture_dir=str(REPO_ROOT / "experiments/ai_crm_next/tests/fixtures/old_user_ops"),
            next_testclient=True,
            include_write_endpoints=False,
            output_md="/tmp/unused.md",
            output_json="/tmp/unused.json",
        )
    )
    return {
        "ok": bool(report.get("ok")),
        "mode": report.get("mode", {}),
        "results": [{"endpoint": item.get("endpoint"), "status": item.get("status"), "issues": item.get("issues", [])} for item in report.get("results", [])],
    }


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    missing_files = [path for path in CONTRACT_FILES + DOCS_TO_SCAN if not (REPO_ROOT / path).exists()]
    if missing_files:
        blockers.append("missing D7.3 files: " + ", ".join(missing_files))

    adapter_contracts = {
        class_name: _class_methods("aicrm_next/integration_gateway/user_ops_adapters.py", class_name)
        if (REPO_ROOT / "aicrm_next/integration_gateway/user_ops_adapters.py").exists()
        else []
        for class_name in REQUIRED_METHODS
    }
    for class_name, required in REQUIRED_METHODS.items():
        missing = [method for method in required if method not in adapter_contracts[class_name]]
        if missing:
            blockers.append(f"{class_name} missing methods: " + ", ".join(missing))

    source = _read("aicrm_next/integration_gateway/user_ops_adapters.py") if (REPO_ROOT / "aicrm_next/integration_gateway/user_ops_adapters.py").exists() else ""
    mode_guards = {
        "default_user_ops_dnd_mode_fake": 'AICRM_NEXT_USER_OPS_DND_MODE", "fake"' in source,
        "default_user_ops_batch_send_mode_fake": 'AICRM_NEXT_USER_OPS_BATCH_SEND_MODE", "fake"' in source,
        "default_wecom_dispatch_mode_fake": 'AICRM_NEXT_WECOM_DISPATCH_MODE", "fake"' in source,
        "default_user_ops_deferred_jobs_mode_fake": 'AICRM_NEXT_USER_OPS_DEFERRED_JOBS_MODE", "fake"' in source,
        "real_user_ops_dnd_env_guard": "AICRM_NEXT_ENABLE_REAL_USER_OPS_DND" in source,
        "real_user_ops_batch_send_env_guard": "AICRM_NEXT_ENABLE_REAL_USER_OPS_BATCH_SEND" in source,
        "real_wecom_dispatch_env_guard": "AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH" in source,
        "real_user_ops_deferred_jobs_env_guard": "AICRM_NEXT_ENABLE_REAL_USER_OPS_DEFERRED_JOBS" in source,
        "production_fail_closed": "production_guard_failed" in source and "production_not_implemented" in source,
    }
    if not all(mode_guards.values()):
        blockers.append("user ops adapter mode guards incomplete")

    runtime = _check_runtime()
    runtime_required = [
        "stable_shape",
        "fake_dnd_deterministic",
        "fake_batch_preview_deterministic",
        "fake_execute_no_dispatch",
        "fake_dispatch_no_send",
        "fake_deferred_no_run",
        "disabled_error",
        "production_guard",
        "production_enabled_not_implemented",
        "side_effect_executed_false",
        "audit_events_created",
        "audit_fields_present",
    ]
    if not all(runtime[key] for key in runtime_required):
        blockers.append("user ops adapter runtime safety check failed")

    app_source = _read("aicrm_next/ops_enrollment/application.py") if (REPO_ROOT / "aicrm_next/ops_enrollment/application.py").exists() else ""
    boundary = {
        "dnd_uses_gateway": "UserOpsDndWriteGateway" in app_source and "enable_do_not_disturb" in app_source and "cancel_do_not_disturb" in app_source,
        "batch_preview_uses_gateway": "build_batch_send_preview" in app_source,
        "batch_execute_uses_gateway": "execute_batch_send" in app_source and "create_send_record" in app_source,
        "dispatch_uses_adapter": "WeComMessageDispatchAdapter" in app_source and "send_private_message" in app_source,
        "deferred_uses_gateway": "UserOpsDeferredJobGateway" in app_source and "run_due_jobs" in app_source,
        "no_old_backend_imports": "wecom_ability_service" not in app_source + source and "openclaw_service" not in app_source + source,
    }
    if not all(boundary.values()):
        blockers.append("user ops application adapter boundary incomplete")

    docs_text = "\n".join(_read(path) for path in DOCS_TO_SCAN if (REPO_ROOT / path).exists())
    forbidden_status_markers = [marker for marker in FORBIDDEN_DOC_MARKERS if marker in docs_text]
    if forbidden_status_markers:
        blockers.append("forbidden D7.3 status markers: " + ", ".join(forbidden_status_markers))

    smoke = _run_user_ops_smoke()
    if not smoke["ok"]:
        blockers.append("user ops smoke failed")

    parity = _run_user_ops_parity()
    if not parity["ok"]:
        blockers.append("user ops parity failed")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "adapter_contracts": adapter_contracts,
        "mode_guards": mode_guards,
        "idempotency": {
            "stable_fake_dnd_result": runtime["fake_dnd_deterministic"],
            "stable_fake_batch_preview_result": runtime["fake_batch_preview_deterministic"],
            "shared_store": "aicrm_next/integration_gateway/idempotency.py",
        },
        "audit": {
            "events_created": runtime["audit_events_created"],
            "fields_present": runtime["audit_fields_present"],
            "shared_sink": "aicrm_next/integration_gateway/audit.py",
        },
        "side_effect_safety": {
            "all_checked_results_side_effect_executed_false": runtime["side_effect_executed_false"],
            **runtime["real_flags"],
        },
        "application_boundary": boundary,
        "user_ops_smoke": smoke,
        "user_ops_parity": parity,
        "recommendation": "D7.3 acceptance ready" if not blockers else "resolve blockers before D7.3 acceptance",
    }


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# D7.3 User Ops Adapter Contract Readiness",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- recommendation: {report['recommendation']}",
        f"- blockers: {len(report['blockers'])}",
        f"- warnings: {len(report['warnings'])}",
        "",
        "## Adapter Contracts",
    ]
    for class_name, methods in report["adapter_contracts"].items():
        lines.append(f"- {class_name}: {', '.join(methods)}")
    lines.extend(
        [
            "",
            "## Mode Guards",
            *[f"- {key}: {value}" for key, value in report["mode_guards"].items()],
            "",
            "## Side Effect Safety",
            *[f"- {key}: {value}" for key, value in report["side_effect_safety"].items()],
            "",
            "## User Ops Smoke",
            f"- ok: {report['user_ops_smoke']['ok']}",
            f"- summary: {json.dumps(report['user_ops_smoke'].get('summary', {}), ensure_ascii=False)}",
            "",
            "## User Ops Parity",
            f"- ok: {report['user_ops_parity']['ok']}",
            "",
            "## Blockers",
            *(([f"- {item}" for item in report["blockers"]] or ["- none"])),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check D7.3 User Ops adapter contract readiness.")
    parser.add_argument("--output-md", required=True, help="Markdown report output path.")
    parser.add_argument("--output-json", required=True, help="JSON report output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
