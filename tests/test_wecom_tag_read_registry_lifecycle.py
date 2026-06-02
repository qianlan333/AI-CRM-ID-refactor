from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
READ_ROUTES = {"/api/admin/wecom/tags", "/api/admin/wecom/tag-groups"}
FAMILY_ROUTES = {"/api/admin/wecom/tags*", "/api/admin/wecom/tag-groups*"}


def _records(path: Path, key: str) -> dict[str, dict]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {record[key]: record for record in payload["routes"]}


def test_wecom_tag_read_routes_are_next_primary_with_legacy_rollback_in_registry() -> None:
    registry = _records(ROOT / "docs/architecture/legacy_exit_route_registry.yaml", "path_pattern")

    for route in READ_ROUTES:
        record = registry[route]
        assert record["runtime_owner"] == "next_native"
        assert record["legacy_fallback_allowed"] is True
        assert record["legacy_source"] == "production_compat"
        assert record["external_side_effect_risk"] == "none"
        assert record["adapter_mode"] == "none"
        assert record["delete_status"] == "next_primary_with_legacy_rollback"
        assert record["replacement_status"] == "validating"


def test_wecom_tag_read_manifest_marks_exact_reads_next_and_families_out_of_scope() -> None:
    manifest = _records(ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml", "route_pattern")

    for route in READ_ROUTES:
        record = manifest[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_exact"
        assert record["legacy_fallback_allowed"] is True
        assert record["external_side_effect_risk"] == "none"
        assert record["delete_ready"] is False
        assert record["delete_status"] == "next_primary_with_legacy_rollback"
        assert record["replacement_status"] == "validating"

    for route in FAMILY_ROUTES:
        record = manifest[route]
        assert record["current_runtime_owner"] == "production_compat"
        assert record["production_behavior"] == "legacy_forward"
        assert record["legacy_fallback_allowed"] is True
        assert record["delete_ready"] is False
