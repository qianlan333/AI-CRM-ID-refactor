from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


EXACT_NEXT_ROUTES = {
    "/auth/wecom/start": "next_primary_with_legacy_rollback",
    "/auth/wecom/callback": "next_primary_with_legacy_rollback",
    "/auth/wecom/unknown": "next_shadow",
    "/api/h5/wechat/oauth/unknown": "next_shadow",
}


def test_auth_wecom_exact_routes_are_next_validating_with_retained_rollback() -> None:
    service = get_route_registry_service()

    for route, delete_status in EXACT_NEXT_ROUTES.items():
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is True
        assert entry.legacy_source == "production_compat"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == delete_status
        assert entry.replacement_status == "validating"
        assert "fallback_used=false" in entry.notes
        assert "real_external_call_executed=false" in entry.notes


def test_auth_wecom_manifest_records_exact_routes_and_retains_wildcards() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route, delete_status in EXACT_NEXT_ROUTES.items():
        record = by_route[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_exact"
        assert record["legacy_fallback_allowed"] is True
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_status"] == delete_status
        assert record["replacement_status"] == "validating"
        assert "fallback_used=false" in record["notes"]
        assert "real_external_call_executed=false" in record["notes"]

    assert by_route["/api/h5/wechat/oauth/start"]["delete_status"] == "deletion_locked"
    assert by_route["/api/h5/wechat/oauth/start"]["legacy_fallback_allowed"] is False
    assert by_route["/api/h5/wechat/oauth/callback"]["delete_status"] == "deletion_locked"
    assert by_route["/api/h5/wechat/oauth/callback"]["legacy_fallback_allowed"] is False

    assert by_route["/api/h5/wechat/oauth*"]["delete_status"] == "active"
    assert by_route["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is True
    assert by_route["/api/h5/wechat/oauth*"]["replacement_status"] == "validating"
    assert by_route["/auth/wecom*"]["delete_status"] == "active"
    assert by_route["/auth/wecom*"]["legacy_fallback_allowed"] is True
    assert by_route["/auth/wecom*"]["replacement_status"] == "validating"
