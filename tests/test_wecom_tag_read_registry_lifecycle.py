from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


READ_ROUTES = {
    "/api/admin/wecom/tags",
    "/api/admin/wecom/tags/{tag_id}",
    "/api/admin/wecom/tag-groups",
    "/api/admin/wecom/tag-groups/{group_id}",
}

WRITE_FAMILIES = {
    "/api/admin/wecom/tags*",
    "/api/admin/wecom/tag-groups*",
}


def test_wecom_tag_read_registry_entries_are_deletion_locked_next_native() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route in READ_ROUTES:
        entry = service.find_route(route, {"GET"})
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.customer_tags"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.external_side_effect_risk == "none"
        assert entry.adapter_mode == "none"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"


def test_wecom_tag_write_and_sync_families_remain_out_of_scope() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route in WRITE_FAMILIES:
        entry = service.find_route(route, {"POST"})
        assert entry is not None
        assert entry.runtime_owner == "production_compat"
        assert entry.legacy_fallback_allowed is True
        assert entry.delete_status == "active"
        assert entry.replacement_status == "not_started"
        assert entry.adapter_mode == "real_blocked"


def test_wecom_tag_live_gate_stays_out_of_scope() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()
    entry = service.find_route("/api/admin/wecom/tags/live/gate", {"GET"})

    assert entry is not None
    assert entry.runtime_owner == "next_native"
    assert entry.legacy_fallback_allowed is False
    assert entry.adapter_mode == "real_blocked"
    assert entry.delete_status == "active"
    assert entry.replacement_status == "not_started"


def test_wecom_tag_read_route_registry_yaml_matches_lifecycle() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    by_route = {record["path_pattern"]: record for record in registry["routes"]}

    for route in READ_ROUTES:
        assert by_route[route]["runtime_owner"] == "next_native"
        assert by_route[route]["legacy_fallback_allowed"] is False
        assert by_route[route]["legacy_source"] == ""
        assert by_route[route]["delete_status"] == "deletion_locked"
        assert by_route[route]["replacement_status"] == "locked"

    for route in WRITE_FAMILIES:
        assert by_route[route]["runtime_owner"] == "production_compat"
        assert by_route[route]["delete_status"] == "active"
        assert by_route[route]["replacement_status"] == "not_started"


def test_wecom_tag_read_production_manifest_locks_read_routes_only() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in READ_ROUTES:
        assert by_route[route]["current_runtime_owner"] == "next"
        assert by_route[route]["production_behavior"] == "next_exact"
        assert by_route[route]["legacy_fallback_allowed"] is False
        assert by_route[route]["delete_ready"] is True
        assert by_route[route]["delete_status"] == "deletion_locked"
        assert by_route[route]["replacement_status"] == "locked"

    for route in WRITE_FAMILIES:
        assert by_route[route]["current_runtime_owner"] == "production_compat"
        assert by_route[route]["production_behavior"] == "legacy_forward"
        assert by_route[route]["legacy_fallback_allowed"] is True
        assert by_route[route]["delete_status"] == "active"
        assert by_route[route]["replacement_status"] == "not_started"
