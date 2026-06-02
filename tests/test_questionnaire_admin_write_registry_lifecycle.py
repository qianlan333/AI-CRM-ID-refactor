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


def test_questionnaire_admin_write_routes_are_locked_next_commandbus_without_rollback() -> None:
    service = get_route_registry_service()

    for route, method in WRITE_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == ""
        assert entry.external_side_effect_risk == "medium"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert "CommandBus" in entry.notes
        assert "legacy rollback removed" in entry.notes


def test_questionnaire_admin_write_manifest_is_locked_next_command_without_rollback() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in ["/api/admin/questionnaires*", "/api/admin/questionnaires/{questionnaire_id}/export"]:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next_command"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["fixture_allowed_in_production"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
        assert record["adapter_mode"] == "real_blocked"
        assert "legacy rollback removed" in record["notes"]
        assert "real_external_call_executed=false" in record["notes"]


def test_questionnaire_h5_group9_locked_and_oauth_wildcard_deleted() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    assert by_route["/api/h5/questionnaires/{slug}/submit"]["delete_ready"] is True
    assert by_route["/api/h5/questionnaires/{slug}/submit"]["replacement_status"] == "locked"
    assert by_route["/api/h5/questionnaires/{slug}/client-diagnostics"]["delete_ready"] is True
    assert by_route["/api/h5/questionnaires/{slug}/client-diagnostics"]["replacement_status"] == "locked"
    assert by_route["/api/h5/wechat/oauth*"]["delete_ready"] is True
    assert by_route["/api/h5/wechat/oauth*"]["delete_status"] == "legacy_deleted"
    assert by_route["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is False
