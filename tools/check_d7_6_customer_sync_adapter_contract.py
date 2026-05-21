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
    "aicrm_next/integration_gateway/customer_sync_contracts.py",
    "aicrm_next/integration_gateway/customer_sync_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
    "aicrm_next/customer_read_model/application.py",
    "aicrm_next/identity_contact/application.py",
    "tools/customer_read_model_gray_smoke.py",
    "tools/compare_customer_read_model_parity.py",
    "experiments/ai_crm_next/tests/fixtures/old_customer_read_model/customers.default.json",
]

DOCS_TO_SCAN = [
    "docs/d7_6_archive_contacts_identity_adapter_contract.md",
    "docs/d7_6_archive_contacts_identity_adapter_implementation_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]

FORBIDDEN_STATUS_MARKERS = ["production_ready", "production_approved", "delete_ready"]

REQUIRED_METHODS: dict[str, list[str]] = {
    "ArchiveSyncAdapter": [
        "fetch_recent_messages",
        "fetch_incremental_archive_messages",
        "normalize_archive_message",
        "build_archive_sync_preview",
        "record_archive_sync_audit",
    ],
    "ContactsSyncAdapter": [
        "fetch_external_contacts",
        "fetch_contact_detail",
        "fetch_follow_user_relations",
        "build_contacts_sync_preview",
        "record_contacts_sync_audit",
    ],
    "IdentityMappingAdapter": [
        "resolve_person_identity",
        "upsert_identity_mapping",
        "link_openid_unionid_external_userid",
        "build_identity_mapping_preview",
        "record_identity_mapping_audit",
    ],
    "CustomerProjectionSyncGateway": [
        "update_customer_list_projection",
        "update_customer_detail_projection",
        "update_customer_timeline_projection",
        "update_recent_messages_projection",
        "build_projection_sync_preview",
        "record_projection_sync_audit",
    ],
}

PRODUCTION_FLAGS = {
    "ArchiveSyncAdapter": "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC",
    "ContactsSyncAdapter": "AICRM_NEXT_ENABLE_REAL_CONTACTS_SYNC",
    "IdentityMappingAdapter": "AICRM_NEXT_ENABLE_REAL_IDENTITY_MAPPING",
    "CustomerProjectionSyncGateway": "AICRM_NEXT_ENABLE_REAL_CUSTOMER_PROJECTION_SYNC",
}


def _path(relpath: str) -> Path:
    return project_path(PROJECT_ROOT, relpath)


def _read(relpath: str) -> str:
    return read_project_text(PROJECT_ROOT, relpath)


def _sample_call(instance: Any) -> Json:
    name = instance.__class__.__name__
    if name == "ArchiveSyncAdapter":
        return instance.fetch_recent_messages(external_userid="wx_ext_001", limit=5)
    if name == "ContactsSyncAdapter":
        return instance.fetch_contact_detail(external_userid="wx_ext_001", follow_user_userid="ZhaoYanFang")
    if name == "IdentityMappingAdapter":
        return instance.resolve_person_identity(external_userid="wx_ext_001", openid="openid_001", unionid="unionid_001")
    if name == "CustomerProjectionSyncGateway":
        return instance.update_recent_messages_projection(external_userid="wx_ext_001", projection_name="recent_messages")
    raise AssertionError(f"unknown adapter {name}")


def _check_adapter_contracts(blockers: list[Json]) -> Json:
    contracts = importlib.import_module("aicrm_next.integration_gateway.customer_sync_contracts")
    adapters = importlib.import_module("aicrm_next.integration_gateway.customer_sync_adapters")
    return check_adapter_methods(adapters, REQUIRED_METHODS, blockers, contracts_module=contracts)


def _check_modes(blockers: list[Json]) -> Json:
    module = importlib.import_module("aicrm_next.integration_gateway.customer_sync_adapters")
    mode_env_names = [
        "AICRM_NEXT_ARCHIVE_SYNC_MODE",
        "AICRM_NEXT_CONTACTS_SYNC_MODE",
        "AICRM_NEXT_IDENTITY_MAPPING_MODE",
        "AICRM_NEXT_CUSTOMER_PROJECTION_SYNC_MODE",
    ]
    with clean_environment(mode_env_names + list(PRODUCTION_FLAGS.values())):
        defaults = {
            "archive_sync": module.build_archive_sync_adapter().mode,
            "contacts_sync": module.build_contacts_sync_adapter().mode,
            "identity_mapping": module.build_identity_mapping_adapter().mode,
            "customer_projection_sync": module.build_customer_projection_sync_gateway().mode,
        }
        if any(mode != "fake" for mode in defaults.values()):
            blockers.append({"reason": "default_mode_not_fake", "defaults": defaults})

        guards = check_adapter_mode_guards(module, PRODUCTION_FLAGS, _sample_call, blockers, defaults)
        source_guards = _check_source_guards(blockers)
        guards.update(source_guards)
        return guards


def _check_idempotency_audit_side_effects(blockers: list[Json]) -> tuple[Json, Json, Json]:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.customer_sync_adapters import (
        ArchiveSyncAdapter,
        ContactsSyncAdapter,
        CustomerProjectionSyncGateway,
        IdentityMappingAdapter,
    )
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store

    reset_audit_events()
    reset_idempotency_store()
    adapters = [
        ArchiveSyncAdapter("fake"),
        ContactsSyncAdapter("fake"),
        IdentityMappingAdapter("fake"),
        CustomerProjectionSyncGateway("fake"),
    ]
    results = [_sample_call(adapter) for adapter in adapters]
    repeated = ArchiveSyncAdapter("fake").fetch_recent_messages(external_userid="wx_ext_001", idempotency_key="d7_6_repeat_key")
    repeated_again = ArchiveSyncAdapter("fake").fetch_recent_messages(external_userid="wx_ext_001", idempotency_key="d7_6_repeat_key")
    events = list_audit_events()
    return check_fake_operation_result_safety(results, repeated, repeated_again, events, blockers)


def _check_docs(blockers: list[Json]) -> tuple[list[Json], list[Json]]:
    return scan_docs_for_forbidden_markers(PROJECT_ROOT, DOCS_TO_SCAN, FORBIDDEN_STATUS_MARKERS, blockers)


def _check_customer_smoke_parity(blockers: list[Json], warnings: list[Json]) -> tuple[Json, Json]:
    try:
        smoke_tool = importlib.import_module("tools.customer_read_model_gray_smoke")
        smoke = smoke_tool.run_smoke(
            Namespace(old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json="")
        )
    except Exception as exc:
        smoke = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "customer_smoke_failed", "error": smoke["error"]})
    try:
        parity_tool = importlib.import_module("tools.compare_customer_read_model_parity")
        parity = parity_tool.run_compare(
            Namespace(
                old_fixture_dir=str(_path("experiments/ai_crm_next/tests/fixtures/old_customer_read_model")),
                old_base_url="",
                next_testclient=True,
                next_base_url="",
                output_md="",
                output_json="",
            )
        )
    except Exception as exc:
        parity = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        blockers.append({"reason": "customer_parity_failed", "error": parity["error"]})
    if not smoke.get("ok"):
        blockers.append({"reason": "customer_smoke_not_ok"})
    if not parity.get("ok"):
        blockers.append({"reason": "customer_parity_not_ok"})
    if smoke.get("ok") and parity.get("ok"):
        warnings.append({"reason": "customer_smoke_and_parity_fixture_mode", "message": "Customer smoke/parity ran in fake fixture/TestClient mode only."})
    return smoke, parity


def _check_source_guards(blockers: list[Json]) -> Json:
    source = _read("aicrm_next/integration_gateway/customer_sync_adapters.py")
    customer_source = _read("aicrm_next/customer_read_model/application.py")
    identity_source = _read("aicrm_next/identity_contact/application.py")
    flags_present = {flag: flag in source for flag in PRODUCTION_FLAGS.values()}
    boundary_present = {
        "archive_sync": "build_archive_sync_adapter" in customer_source,
        "contacts_sync": "build_contacts_sync_adapter" in customer_source,
        "identity_mapping": "build_identity_mapping_adapter" in identity_source,
        "customer_projection": "build_customer_projection_sync_gateway" in customer_source,
    }
    if not all(flags_present.values()):
        blockers.append({"reason": "missing_production_guard_flag", "flags": flags_present})
    if not all(boundary_present.values()):
        blockers.append({"reason": "customer_sync_application_boundary_missing", "boundary_present": boundary_present})
    return {"flags_present": flags_present, "application_boundary_present": boundary_present}


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    missing_files = collect_missing_files(PROJECT_ROOT, CONTRACT_FILES, blockers, reason="missing_required_file")
    adapter_contracts = _check_adapter_contracts(blockers)
    mode_guards = _check_modes(blockers)
    idempotency, audit, side_effect_safety = _check_idempotency_audit_side_effects(blockers)
    missing_docs, forbidden_status_markers = _check_docs(blockers)
    customer_smoke, customer_parity = _check_customer_smoke_parity(blockers, warnings)
    recommendation = (
        "D7.6 Customer sync adapter contract is fake-contract ready; proceed to D7.6 validation review before any WeCom archive, contacts, identity, or projection production work."
        if not blockers
        else "Do not proceed; resolve D7.6 Customer sync adapter contract blockers first."
    )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "adapter_contracts": adapter_contracts,
        "mode_guards": mode_guards,
        "idempotency": idempotency,
        "audit": audit,
        "side_effect_safety": side_effect_safety,
        "customer_smoke": {"ok": bool(customer_smoke.get("ok")), "mode": customer_smoke.get("mode")},
        "customer_parity": {"ok": bool(customer_parity.get("ok")), "mode": customer_parity.get("mode")},
        "missing_files": missing_files,
        "missing_docs": missing_docs,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": recommendation,
    }


def write_markdown_report(report: Json, path: Path) -> None:
    lines = [
        "# D7.6 Customer Sync Adapter Contract Check",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- blockers: {len(report['blockers'])}",
        f"- warnings: {len(report['warnings'])}",
        f"- customer_smoke: {'PASS' if report['customer_smoke']['ok'] else 'FAIL'}",
        f"- customer_parity: {'PASS' if report['customer_parity']['ok'] else 'FAIL'}",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- `{item['reason']}`: {json.dumps(item, ensure_ascii=False)}" for item in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Recommendation", "", report["recommendation"]])
    write_markdown_lines(path, lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check D7.6 customer sync adapter contract readiness.")
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
