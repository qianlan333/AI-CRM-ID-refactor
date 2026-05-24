from __future__ import annotations

import json

from tools import check_phase4f_profile_segment_template_schema_confirmation as checker


def test_phase4f_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_phase4f_authorization_flags_false() -> None:
    data = checker.load_yaml()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_phase4f_confirmed_tables_complete() -> None:
    result = checker.check_confirmed_tables()
    assert result["ok"], result
    tables = {item["name"] for item in checker.load_yaml()["confirmed_tables"]}
    assert checker.REQUIRED_TABLES.issubset(tables)


def test_phase4f_confirmed_services_complete() -> None:
    result = checker.check_confirmed_services()
    assert result["ok"], result
    services = {item["function"] for item in checker.load_yaml()["confirmed_services"]}
    assert checker.REQUIRED_SERVICES.issubset(services)


def test_phase4f_field_mapping_includes_required_next_fields() -> None:
    result = checker.check_field_mapping_confirmation()
    assert result["ok"], result
    fields = {item["next_field"] for item in checker.load_yaml()["field_mapping_confirmation"]}
    assert checker.REQUIRED_NEXT_FIELDS.issubset(fields)


def test_phase4f_idempotency_confirmation_explicit() -> None:
    result = checker.check_idempotency_confirmation()
    assert result["ok"], result
    idem = checker.load_yaml()["idempotency_confirmation"]
    assert idem["existing_storage_confirmed"] in {True, False}
    assert idem["recommended_path"]
    assert idem["notes"]


def test_phase4f_audit_confirmation_explicit() -> None:
    result = checker.check_audit_confirmation()
    assert result["ok"], result
    audit = checker.load_yaml()["audit_confirmation"]
    assert audit["operator_snapshot_confirmed"] is True
    assert audit["dedicated_audit_storage_confirmed"] in {True, False}
    assert audit["before_after_snapshot_storage_confirmed"] in {True, False}


def test_phase4f_repository_feasibility_decision_allowed() -> None:
    result = checker.check_repository_adapter_feasibility()
    assert result["ok"], result
    decision = checker.load_yaml()["repository_adapter_feasibility"]["decision"]
    assert decision in checker.ALLOWED_FEASIBILITY_DECISIONS


def test_phase4f_phase4g_recommendation_is_guarded() -> None:
    result = checker.check_phase4g_recommendation()
    assert result["ok"], result
    recommendation = checker.load_yaml()["phase_4g_recommendation"]
    assert recommendation["direct_route_switch_allowed"] is False
    assert recommendation["production_route_owner_switch_allowed"] is False
    assert recommendation["production_repository_allowed_without_owner_approval"] is False
    assert recommendation["migration_allowed_without_owner_approval"] is False


def test_phase4f_source_crosscheck_confirms_tables_and_services() -> None:
    result = checker.check_source_crosscheck()
    assert result["ok"], result


def test_phase4f_no_runtime_files_changed_if_git_available() -> None:
    result = checker.check_no_runtime_changes()
    assert result["ok"], result


def test_phase4f_docs_do_not_claim_approval_or_cutover() -> None:
    result = checker.check_doc_claims()
    assert result["ok"], result
