from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


OAUTH_ROUTES = {
    ("/api/h5/wechat/oauth/start", "GET"),
    ("/api/h5/wechat/oauth/callback", "GET"),
}


def test_questionnaire_oauth_routes_are_next_adapter_validating_with_rollback() -> None:
    service = get_route_registry_service()

    for route, method in OAUTH_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_adapter"
        assert entry.legacy_fallback_allowed is True
        assert entry.legacy_source == "production_compat"
        assert entry.external_side_effect_risk == "medium"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "next_primary_with_legacy_rollback"
        assert entry.replacement_status == "validating"
        assert "Next OAuth adapter primary" in entry.notes


def test_questionnaire_oauth_manifest_is_next_adapter_validating_with_rollback() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in ["/api/h5/wechat/oauth/start", "/api/h5/wechat/oauth/callback"]:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next_adapter"
        assert record["production_behavior"] == "next_oauth_adapter"
        assert record["legacy_fallback_allowed"] is True
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_status"] == "next_primary_with_legacy_rollback"
        assert record["replacement_status"] == "validating"
        assert "no real OAuth default" in record["notes"]


def test_questionnaire_oauth_wildcard_and_auth_wecom_stay_out_of_scope() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    assert by_route["/api/h5/wechat/oauth*"]["current_runtime_owner"] == "production_compat"
    assert by_route["/api/h5/wechat/oauth*"]["delete_status"] == "active"
    assert by_route["/auth/wecom*"]["current_runtime_owner"] == "production_compat"
    assert by_route["/auth/wecom*"]["delete_status"] == "active"
