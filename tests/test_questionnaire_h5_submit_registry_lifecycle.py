from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


H5_COMMAND_ROUTES = {
    ("/api/h5/questionnaires/{slug}/submit", "POST"),
    ("/api/h5/questionnaires/{slug}/client-diagnostics", "POST"),
}


def test_questionnaire_h5_submit_routes_are_next_command_with_legacy_rollback() -> None:
    service = get_route_registry_service()

    for route, method in H5_COMMAND_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is True
        assert entry.legacy_source == "production_compat"
        assert entry.external_side_effect_risk == "medium"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "next_primary_with_legacy_rollback"
        assert entry.replacement_status == "validating"
        assert "CommandBus" in entry.notes
        assert "real_external_call_executed=false" in entry.notes


def test_questionnaire_h5_submit_manifest_is_next_command_validating_with_rollback() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in ["/api/h5/questionnaires/{slug}/submit", "/api/h5/questionnaires/{slug}/client-diagnostics"]:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next_command"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is True
        assert record["fixture_allowed_in_production"] is False
        assert record["delete_ready"] is False
        assert record["delete_status"] == "next_primary_with_legacy_rollback"
        assert record["replacement_status"] == "validating"
        assert record["adapter_mode"] == "real_blocked"
        assert "legacy rollback remains allowed" in record["notes"]
        assert "real_external_call_executed=false" in record["notes"]


def test_questionnaire_oauth_and_admin_read_write_lifecycle_boundaries_remain_intact() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    by_path = {record["path_pattern"]: record for record in registry["routes"]}

    assert by_path["/api/h5/wechat/oauth*"]["delete_status"] == "active"
    assert by_path["/api/h5/wechat/oauth*"]["replacement_status"] == "not_started"
    assert by_path["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is True

    for route in ["/api/admin/questionnaires", "/api/admin/questionnaires*"]:
        assert by_path[route]["delete_status"] == "deletion_locked"
        assert by_path[route]["replacement_status"] == "locked"
