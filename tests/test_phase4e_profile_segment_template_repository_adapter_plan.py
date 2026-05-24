from __future__ import annotations

import json

from tools import check_phase4e_profile_segment_template_repository_adapter_plan as checker


def test_phase4e_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_phase4e_authorization_flags_false() -> None:
    data = checker.load_yaml()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_phase4e_route_family_and_owner_match() -> None:
    data = checker.load_yaml()
    assert data["route_family"] == checker.EXPECTED_ROUTE_FAMILY
    assert data["capability_owner"] == checker.EXPECTED_CAPABILITY_OWNER
    assert data["integration_fallback_boundary"] == checker.EXPECTED_FALLBACK_BOUNDARY


def test_phase4e_legacy_discovery_has_routes_or_unknowns() -> None:
    result = checker.check_legacy_discovery()
    assert result["ok"], result


def test_phase4e_field_mapping_includes_required_next_fields() -> None:
    result = checker.check_field_mapping()
    assert result["ok"], result


def test_phase4e_repository_strategy_options_complete() -> None:
    result = checker.check_repository_strategy()
    assert result["ok"], result
    strategy = checker.load_yaml()["repository_strategy"]
    option_ids = {item["id"] for item in strategy["options"]}
    assert checker.REQUIRED_STRATEGIES.issubset(option_ids)


def test_phase4e_repository_contract_methods_and_write_guards() -> None:
    result = checker.check_repository_contract()
    assert result["ok"], result
    methods = {
        item["name"]: item
        for item in checker.load_yaml()["planned_repository_contract"]["methods"]
    }
    assert checker.REQUIRED_METHODS.issubset(methods)
    create = methods["create_profile_segment_template"]
    assert create["transaction_required"] is True
    assert create["idempotency_required"] is True
    assert create["audit_required"] is True
    assert create["rollback_required"] is True
    assert create["validation_boundary"]
    update = methods["update_profile_segment_template"]
    assert update["transaction_required"] is True
    assert update["audit_required"] is True
    assert update["rollback_required"] is True
    assert update["validation_boundary"]


def test_phase4e_idempotency_audit_rollback_and_parity_complete() -> None:
    result = checker.check_designs_and_parity()
    assert result["ok"], result


def test_phase4e_phase4f_recommendation_is_guarded() -> None:
    result = checker.check_phase4f_recommendation()
    assert result["ok"], result


def test_phase4e_no_runtime_files_changed_if_git_available() -> None:
    result = checker.check_no_runtime_changes()
    assert result["ok"], result


def test_phase4e_docs_do_not_claim_approval_or_cutover() -> None:
    result = checker.check_doc_claims()
    assert result["ok"], result
