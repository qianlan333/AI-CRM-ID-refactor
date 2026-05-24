from __future__ import annotations

import json

from tools import check_phase4d_profile_segment_template_production_switch_plan as checker


def test_phase4d_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_phase4d_authorization_flags_false() -> None:
    data = checker.load_yaml()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_phase4d_route_family_and_owners() -> None:
    data = checker.load_yaml()
    assert data["route_family"] == checker.EXPECTED_ROUTE_FAMILY
    assert data["capability_owner"] == checker.EXPECTED_CAPABILITY_OWNER
    assert data["integration_fallback_boundary"] == checker.EXPECTED_FALLBACK_BOUNDARY


def test_phase4d_forbidden_scope_and_planned_routes_complete() -> None:
    data = checker.load_yaml()
    scope = data["scope"]
    assert checker.REQUIRED_FORBIDDEN_SCOPE.issubset(set(scope["forbidden"]))
    planned = {(item["method"], item["path"]) for item in scope["planned_routes"]}
    assert checker.EXPECTED_ROUTES.issubset(planned)


def test_phase4d_repository_strategy_has_required_options() -> None:
    strategy = checker.load_yaml()["repository_strategy"]
    options = {item["id"]: item for item in strategy["options"]}
    assert {"reuse_legacy_tables", "new_next_tables"}.issubset(options)
    for option in options.values():
        assert option["pros"]
        assert option["cons"]
        assert option["risks"]
    assert strategy["selected_strategy"] or strategy["selection_status"] == "pending_owner_approval"


def test_phase4d_route_ownership_does_not_switch_production() -> None:
    ownership = checker.load_yaml()["route_ownership_strategy"]
    assert ownership["production_switch_in_phase_4d"] is False
    assert ownership["fallback_retained"] is True
    for item in checker.REQUIRED_ROUTE_SEQUENCE:
        assert item in ownership["recommended_sequence"]


def test_phase4d_parity_smoke_and_rollback_plans_complete() -> None:
    data = checker.load_yaml()
    assert checker.REQUIRED_PARITY.issubset(set(data["parity_plan"]["required"]))
    assert data["parity_plan"]["write_dual_run_authorized"] is False
    assert checker.REQUIRED_SMOKE.issubset(set(data["production_smoke_plan"]["required"]))
    assert checker.REQUIRED_ROLLBACK.issubset(set(data["rollback_plan"]["required"]))


def test_phase4d_legacy_registration_and_production_compat_fallback_exist() -> None:
    assert checker.check_legacy_route_registration()["ok"]
    assert checker.check_production_compat_fallback()["ok"]


def test_phase4d_no_runtime_files_changed_if_git_available() -> None:
    result = checker.check_no_runtime_changes()
    assert result["ok"], result


def test_phase4d_docs_do_not_claim_cutover_or_approval() -> None:
    assert checker.check_doc_claims()["ok"]
