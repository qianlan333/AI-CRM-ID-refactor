from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


WRITE_ROUTES = {
    ("/api/admin/questionnaires", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}", "PUT"),
    ("/api/admin/questionnaires/{questionnaire_id}", "PATCH"),
    ("/api/admin/questionnaires/{questionnaire_id}", "DELETE"),
    ("/api/admin/questionnaires/{questionnaire_id}/duplicate", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/publish", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/enable", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/disable", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/export/preview", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/export", "GET"),
}


def test_questionnaire_admin_write_routes_are_validating_next_commandbus_with_rollback() -> None:
    service = get_route_registry_service()

    for route, method in WRITE_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is True
        assert entry.external_side_effect_risk == "medium"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "next_primary_with_legacy_rollback"
        assert entry.replacement_status == "validating"
        assert "CommandBus" in entry.notes
        assert "legacy rollback retained until validation" in entry.notes


def test_questionnaire_admin_write_manifest_is_next_command_not_delete_locked() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in ["/api/admin/questionnaires*", "/api/admin/questionnaires/{questionnaire_id}/export"]:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is True
        assert record["fixture_allowed_in_production"] is False
        assert record["delete_ready"] is False
        assert record["delete_status"] == "next_primary_with_legacy_rollback"
        assert record["replacement_status"] == "validating"
        assert record["adapter_mode"] == "real_blocked"
        assert "real_external_call_executed=false" in record["notes"]


def test_questionnaire_h5_and_oauth_are_not_locked_by_admin_write_group() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    assert by_route["/api/h5/questionnaires/{slug}/submit"]["delete_ready"] is False
    assert by_route["/api/h5/wechat/oauth*"]["delete_ready"] is False
