from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_campaign_read_registry_is_next_read_model_locked():
    record = next(item for item in _records(REGISTRY) if item.get("route_id") == "cloud_orchestrator_campaigns_read_family")

    assert record["path_pattern"] == "/api/admin/cloud-orchestrator/campaigns*"
    assert record["methods"] == ["GET"]
    assert record["runtime_owner"] == "next_read_model"
    assert record["legacy_fallback_allowed"] is False
    assert record["legacy_source"] == ""
    assert record["external_side_effect_risk"] == "none"
    assert record["adapter_mode"] == "none"
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "legacy rollback removed" in record["notes"]
    assert "no real WeCom send" in record["notes"]
    assert "no automation runtime" in record["notes"]


def test_campaign_page_registry_is_locked_over_next_read_apis():
    record = next(item for item in _records(REGISTRY) if item.get("route_id") == "cloud_orchestrator_campaigns_page")

    assert record["path_pattern"] == "/admin/cloud-orchestrator/campaigns"
    assert record["methods"] == ["GET"]
    assert record["runtime_owner"] == "frontend_compat over Next read APIs"
    assert record["legacy_fallback_allowed"] is False
    assert record["legacy_source"] == ""
    assert record["external_side_effect_risk"] == "none"
    assert record["adapter_mode"] == "none"
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "write controls remain disabled" in record["notes"]


def test_campaign_write_registry_stays_out_of_scope_active():
    record = next(item for item in _records(REGISTRY) if item.get("route_id") == "cloud_orchestrator_campaigns_write_legacy_family")

    assert record["methods"] == ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    assert record["runtime_owner"] == "production_compat"
    assert record["legacy_fallback_allowed"] is True
    assert record["delete_status"] == "active"
    assert record["replacement_status"] == "not_started"
    assert "deletion_locked" in record["notes"]
    assert "out of scope" in record["notes"]


def test_campaign_manifest_read_write_and_run_due_states():
    records = _records(MANIFEST)
    read = next(item for item in records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns*" and item.get("methods") == ["GET"])
    write = next(item for item in records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns*" and item.get("methods") == ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    run_due = next(item for item in records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns/run-due*")

    assert read["current_runtime_owner"] == "next"
    assert read["production_behavior"] == "next_exact"
    assert read["legacy_fallback_allowed"] is False
    assert read["external_side_effect_risk"] == "none"
    assert read["delete_ready"] is True
    assert read["delete_status"] == "deletion_locked"
    assert read["replacement_status"] == "locked"

    assert write["current_runtime_owner"] == "production_compat"
    assert write["production_behavior"] == "legacy_forward"
    assert write["legacy_fallback_allowed"] is True
    assert write["delete_status"] == "active"
    assert write["replacement_status"] == "not_started"

    assert run_due["current_runtime_owner"] == "production_compat"
    assert run_due["production_behavior"] == "scheduled_safe_mode"
    assert run_due["delete_ready"] is False


def test_campaign_page_manifest_is_locked():
    record = next(item for item in _records(MANIFEST) if item.get("route_pattern") == "/admin/cloud-orchestrator/campaigns")

    assert record["methods"] == ["GET"]
    assert record["current_runtime_owner"] == "next"
    assert record["production_behavior"] == "next_exact"
    assert record["legacy_fallback_allowed"] is False
    assert record["delete_ready"] is True
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"


def test_media_upload_locked_state_does_not_regress():
    registry_record = next(item for item in _records(REGISTRY) if item.get("route_id") == "cloud_orchestrator_media_upload_adapter")
    manifest_record = next(item for item in _records(MANIFEST) if item.get("route_pattern") == "/api/admin/cloud-orchestrator/media/upload")

    assert registry_record["delete_status"] == "deletion_locked"
    assert registry_record["replacement_status"] == "locked"
    assert registry_record["legacy_fallback_allowed"] is False
    assert manifest_record["delete_status"] == "deletion_locked"
    assert manifest_record["replacement_status"] == "locked"
    assert manifest_record["legacy_fallback_allowed"] is False
