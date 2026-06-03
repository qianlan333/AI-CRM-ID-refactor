from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


WRITE_ROUTES = {
    ("/api/admin/wecom/tags", "POST"),
    ("/api/admin/wecom/tags/{tag_id}", "PATCH"),
    ("/api/admin/wecom/tags/{tag_id}", "DELETE"),
    ("/api/admin/wecom/tags/sync", "POST"),
    ("/api/admin/wecom/tags/sync-due", "POST"),
    ("/api/admin/wecom/tag-groups", "POST"),
    ("/api/admin/wecom/tag-groups/{group_id}", "PATCH"),
    ("/api/admin/wecom/tag-groups/{group_id}", "DELETE"),
}

ROLLBACK_FAMILIES = {
    "/api/admin/wecom/tags*",
    "/api/admin/wecom/tag-groups*",
}


def test_wecom_tag_write_registry_entries_are_next_command_with_rollback() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route, method in WRITE_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.customer_tags"
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is True
        assert entry.legacy_source == "production_compat"
        assert entry.external_side_effect_risk == "high"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "next_primary_with_legacy_rollback"
        assert entry.replacement_status == "validating"


def test_wecom_tag_write_rollback_families_remain_active() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route in ROLLBACK_FAMILIES:
        entry = service.find_route(route, {"POST"})
        assert entry is not None
        assert entry.runtime_owner == "production_compat"
        assert entry.legacy_fallback_allowed is True
        assert entry.delete_status == "active"
        assert entry.replacement_status == "validating"


def test_wecom_tag_write_yaml_registry_and_manifest_lifecycle() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    registry_by_route = {(record["path_pattern"], tuple(record["methods"])): record for record in registry["routes"]}
    manifest_by_route = {(record["route_pattern"], tuple(record["methods"])): record for record in manifest["routes"]}

    exact_routes = [
        ("/api/admin/wecom/tags", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tags/{tag_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
        ("/api/admin/wecom/tags/sync", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tags/sync-due", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tag-groups", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tag-groups/{group_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
    ]

    for route in exact_routes:
        registry_record = registry_by_route[route]
        manifest_record = manifest_by_route[route]
        assert registry_record["runtime_owner"] == "next_command"
        assert registry_record["legacy_fallback_allowed"] is True
        assert registry_record["delete_status"] == "next_primary_with_legacy_rollback"
        assert registry_record["replacement_status"] == "validating"
        assert manifest_record["current_runtime_owner"] == "next"
        assert manifest_record["production_behavior"] == "next_command"
        assert manifest_record["legacy_fallback_allowed"] is True
        assert manifest_record["delete_status"] == "next_primary_with_legacy_rollback"
        assert manifest_record["replacement_status"] == "validating"
