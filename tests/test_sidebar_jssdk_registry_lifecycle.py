from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


ROUTE = "/api/sidebar/jssdk-config"


def test_sidebar_jssdk_registry_entry_is_next_adapter_validating_with_rollback() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for methods in [{"GET"}, {"HEAD"}, {"OPTIONS"}]:
        entry = service.find_route(ROUTE, methods)
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.identity_contact"
        assert entry.runtime_owner == "next_adapter"
        assert entry.legacy_fallback_allowed is True
        assert entry.legacy_source == "production_compat"
        assert entry.external_side_effect_risk == "high"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "next_primary_with_legacy_rollback"
        assert entry.replacement_status == "validating"


def test_sidebar_jssdk_manifest_matches_group15_lifecycle() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    registry_record = next(record for record in registry["routes"] if record["path_pattern"] == ROUTE)
    manifest_record = next(record for record in manifest["routes"] if record["route_pattern"] == ROUTE)

    assert registry_record["methods"] == ["GET", "HEAD", "OPTIONS"]
    assert registry_record["runtime_owner"] == "next_adapter"
    assert registry_record["legacy_fallback_allowed"] is True
    assert registry_record["delete_status"] == "next_primary_with_legacy_rollback"
    assert registry_record["replacement_status"] == "validating"
    assert registry_record["adapter_mode"] == "real_blocked"
    assert manifest_record["methods"] == ["GET", "HEAD", "OPTIONS"]
    assert manifest_record["current_runtime_owner"] == "next_adapter"
    assert manifest_record["production_behavior"] == "next_adapter"
    assert manifest_record["legacy_fallback_allowed"] is True
    assert manifest_record["delete_ready"] is False
    assert manifest_record["adapter_mode"] == "real_blocked"
