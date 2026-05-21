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
    "aicrm_next/integration_gateway/questionnaire_contracts.py",
    "aicrm_next/integration_gateway/questionnaire_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
    "aicrm_next/questionnaire/application.py",
    "tools/questionnaire_readonly_gray_smoke.py",
    "tools/compare_questionnaire_parity.py",
    "experiments/ai_crm_next/tests/fixtures/old_questionnaire/submit.default.json",
]
DOCS_TO_SCAN = [
    "docs/d7_2_questionnaire_submit_oauth_wecom_tag_adapter_contract.md",
    "docs/d7_2_questionnaire_adapter_implementation_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]
REQUIRED_METHODS = {
    "WeChatOAuthAdapter": ["build_authorize_url", "exchange_code", "fetch_userinfo", "resolve_oauth_identity"],
    "WeComTagAdapter": ["mark_external_contact_tags", "unmark_external_contact_tags", "validate_tag_ids", "build_tag_operation_preview"],
    "QuestionnaireExternalPushAdapter": ["push_submission_event", "push_score_result_event", "retry_push_event", "build_push_preview"],
    "QuestionnaireSubmitSideEffectGateway": ["apply_tags", "emit_external_push", "emit_automation_questionnaire_result", "record_side_effect_audit"],
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
    from aicrm_next.integration_gateway.questionnaire_adapters import (
        QuestionnaireExternalPushAdapter,
        QuestionnaireSubmitSideEffectGateway,
        WeChatOAuthAdapter,
        WeComTagAdapter,
    )

    reset_audit_events()
    reset_idempotency_store()
    oauth_a = WeChatOAuthAdapter("fake").resolve_oauth_identity(state="hxc-activation-v1", code="code-1")
    oauth_b = WeChatOAuthAdapter("fake").resolve_oauth_identity(state="hxc-activation-v1", code="code-1")
    tag_a = WeComTagAdapter("fake").mark_external_contact_tags(
        external_userid="external_1",
        tag_ids=["tag_b", "tag_a"],
        questionnaire_id=1,
        submission_id="sub_1",
    )
    tag_b = WeComTagAdapter("fake").mark_external_contact_tags(
        external_userid="external_1",
        tag_ids=["tag_a", "tag_b"],
        questionnaire_id=1,
        submission_id="sub_1",
    )
    push_a = QuestionnaireExternalPushAdapter("fake").push_submission_event(
        questionnaire_id=1,
        submission_id="sub_1",
        webhook_url="https://example.invalid/hook",
        payload_summary={"score": 10},
    )
    push_b = QuestionnaireExternalPushAdapter("fake").push_submission_event(
        questionnaire_id=1,
        submission_id="sub_1",
        webhook_url="https://example.invalid/hook",
        payload_summary={"score": 10},
    )
    disabled = WeComTagAdapter("disabled").mark_external_contact_tags(external_userid="external_1", tag_ids=["tag_a"])
    staging = QuestionnaireExternalPushAdapter("staging").build_push_preview(questionnaire_id=1, webhook_url="https://example.invalid/hook")

    previous_env = os.environ.pop("AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH", None)
    try:
        guarded = WeChatOAuthAdapter("production").exchange_code(code="code-1", state="hxc-activation-v1")
    finally:
        if previous_env is not None:
            os.environ["AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH"] = previous_env

    gateway = QuestionnaireSubmitSideEffectGateway(tag_adapter=WeComTagAdapter("fake"), push_adapter=QuestionnaireExternalPushAdapter("fake"))
    gateway_tag = gateway.apply_tags(questionnaire_id=1, submission_id="sub_1", external_userid="external_1", tag_ids=["tag_a"])
    gateway_push = gateway.emit_external_push(
        questionnaire_id=1,
        submission_id="sub_1",
        webhook_url="https://example.invalid/hook",
        payload_summary={"score": 10},
    )
    events = list_audit_events()
    checked_results = [oauth_a, oauth_b, tag_a, tag_b, push_a, push_b, disabled, staging, guarded, gateway_tag, gateway_push]
    return {
        "stable_shape": all(all(field in item for field in REQUIRED_RESULT_FIELDS) for item in checked_results),
        "fake_oauth_deterministic": oauth_a["result"] == oauth_b["result"],
        "fake_tag_deterministic": tag_a["result"] == tag_b["result"],
        "fake_push_deterministic": push_a["result"] == push_b["result"],
        "disabled_error": disabled["ok"] is False and disabled["error_code"] == "adapter_disabled",
        "production_guard": guarded["ok"] is False and guarded["error_code"] == "production_guard_failed",
        "side_effect_executed_false": all(item["side_effect_executed"] is False for item in checked_results),
        "audit_events_created": len(events) >= len(checked_results) and all(event.get("audit_id") for event in events),
        "audit_fields_present": all(
            {"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event)
            for event in events
        ),
        "real_flags": {
            "real_oauth_executed": False,
            "real_wecom_tag_executed": False,
            "real_external_webhook_executed": False,
        },
    }


def _run_questionnaire_smoke() -> dict[str, Any]:
    from tools import questionnaire_readonly_gray_smoke as smoke

    report = smoke.run_smoke(
        Namespace(
            old_base_url="",
            next_testclient=True,
            next_base_url="",
            include_fake_submit=True,
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


def _run_questionnaire_parity() -> dict[str, Any]:
    from tools import compare_questionnaire_parity as parity

    report = parity.run_compare(
        Namespace(
            old_base_url="",
            next_base_url="",
            old_fixture_dir=str(REPO_ROOT / "experiments/ai_crm_next/tests/fixtures/old_questionnaire"),
            next_testclient=True,
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
        blockers.append("missing D7.2 files: " + ", ".join(missing_files))

    adapter_contracts = {
        class_name: _class_methods("aicrm_next/integration_gateway/questionnaire_adapters.py", class_name)
        if (REPO_ROOT / "aicrm_next/integration_gateway/questionnaire_adapters.py").exists()
        else []
        for class_name in REQUIRED_METHODS
    }
    for class_name, required in REQUIRED_METHODS.items():
        missing = [method for method in required if method not in adapter_contracts[class_name]]
        if missing:
            blockers.append(f"{class_name} missing methods: " + ", ".join(missing))

    source = _read("aicrm_next/integration_gateway/questionnaire_adapters.py") if (REPO_ROOT / "aicrm_next/integration_gateway/questionnaire_adapters.py").exists() else ""
    mode_guards = {
        "default_wechat_oauth_mode_fake": 'AICRM_NEXT_WECHAT_OAUTH_MODE", "fake"' in source,
        "default_wecom_tag_mode_fake": 'AICRM_NEXT_WECOM_TAG_MODE", "fake"' in source,
        "default_questionnaire_webhook_mode_fake": 'AICRM_NEXT_QUESTIONNAIRE_WEBHOOK_MODE", "fake"' in source,
        "real_wechat_oauth_env_guard": "AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH" in source,
        "real_wecom_tag_env_guard": "AICRM_NEXT_ENABLE_REAL_WECOM_TAG" in source,
        "real_questionnaire_webhook_env_guard": "AICRM_NEXT_ENABLE_REAL_QUESTIONNAIRE_WEBHOOK" in source,
        "production_fail_closed": "production_guard_failed" in source and "production_not_implemented" in source,
    }
    if not all(mode_guards.values()):
        blockers.append("questionnaire adapter mode guards incomplete")

    runtime = _check_runtime()
    runtime_required = [
        "stable_shape",
        "fake_oauth_deterministic",
        "fake_tag_deterministic",
        "fake_push_deterministic",
        "disabled_error",
        "production_guard",
        "side_effect_executed_false",
        "audit_events_created",
        "audit_fields_present",
    ]
    if not all(runtime[key] for key in runtime_required):
        blockers.append("questionnaire adapter runtime safety check failed")

    app_source = _read("aicrm_next/questionnaire/application.py") if (REPO_ROOT / "aicrm_next/questionnaire/application.py").exists() else ""
    oauth_source = _read("aicrm_next/questionnaire/oauth.py") if (REPO_ROOT / "aicrm_next/questionnaire/oauth.py").exists() else ""
    boundary = {
        "submit_uses_side_effect_gateway": "QuestionnaireSubmitSideEffectGateway" in app_source and "apply_tags" in app_source and "emit_external_push" in app_source,
        "oauth_start_uses_adapter_boundary": "build_wechat_oauth_adapter" in app_source and "build_authorize_url" in app_source,
        "oauth_legacy_fake_adapter_delegates": "build_wechat_oauth_adapter" in oauth_source and "resolve_oauth_identity" in oauth_source,
        "no_old_backend_imports": "wecom_ability_service" not in app_source + source + oauth_source and "openclaw_service" not in app_source + source + oauth_source,
    }
    if not all(boundary.values()):
        blockers.append("questionnaire application adapter boundary incomplete")

    docs_text = "\n".join(_read(path) for path in DOCS_TO_SCAN if (REPO_ROOT / path).exists())
    forbidden_status_markers = [marker for marker in FORBIDDEN_DOC_MARKERS if marker in docs_text]
    if forbidden_status_markers:
        blockers.append("forbidden D7.2 status markers: " + ", ".join(forbidden_status_markers))

    smoke = _run_questionnaire_smoke()
    if not smoke["ok"]:
        blockers.append("questionnaire smoke failed")

    parity = _run_questionnaire_parity()
    if not parity["ok"]:
        blockers.append("questionnaire parity failed")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "adapter_contracts": adapter_contracts,
        "mode_guards": mode_guards,
        "idempotency": {
            "deterministic_fake_results": runtime["fake_oauth_deterministic"] and runtime["fake_tag_deterministic"] and runtime["fake_push_deterministic"],
        },
        "audit": {
            "audit_events_created": runtime["audit_events_created"],
            "audit_fields_present": runtime["audit_fields_present"],
        },
        "side_effect_safety": {
            "side_effect_executed_false": runtime["side_effect_executed_false"],
            **runtime["real_flags"],
        },
        "questionnaire_smoke": smoke,
        "questionnaire_parity": parity,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": "READY_FOR_D7_2_ACCEPTANCE" if not blockers else "FIX_D7_2_QUESTIONNAIRE_ADAPTER_BLOCKERS",
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# D7.2 Questionnaire Adapter Contract Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        "",
        "## Blockers",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- none"])
    for section in (
        "adapter_contracts",
        "mode_guards",
        "idempotency",
        "audit",
        "side_effect_safety",
        "questionnaire_smoke",
        "questionnaire_parity",
    ):
        lines.extend(["", f"## {section}", "", "```json", json.dumps(report[section], ensure_ascii=False, indent=2), "```"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D7.2 Questionnaire submit / OAuth / WeCom tag / external push adapter contract.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    report = build_report()
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.output_md))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
