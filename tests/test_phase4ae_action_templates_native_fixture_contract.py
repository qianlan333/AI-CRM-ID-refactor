from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import tools.check_phase4ae_action_templates_native_fixture_contract as checker


ROOT = Path(__file__).resolve().parents[1]


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.automation_engine.action_template_repository import reset_action_template_fixture_state
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_action_template_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_non_production_get_list_works(client) -> None:
    response = client.get("/api/admin/automation-conversion/action-templates")

    assert response.status_code == 200
    body = response.json()
    assert body["route_owner"] == "ai_crm_next"
    assert body["source_status"] == "fixture_local_contract"
    assert body["count"] >= 1
    assert _all_real_safety_false(body)


def test_non_production_post_create_works(client) -> None:
    response = client.post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "Phase 4AE Create",
            "template_code": "phase4ae_create",
            "idempotency_key": "create-key",
            "operator": "pytest",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["template"]["template_code"] == "phase4ae_create"
    assert body["idempotent_replay"] is False
    assert _all_real_safety_false(body)


def test_create_idempotency_replay_works(client) -> None:
    payload = {
        "template_name": "Phase 4AE Replay",
        "template_code": "phase4ae_replay",
        "idempotency_key": "replay-key",
        "operator": "pytest",
    }

    created = client.post("/api/admin/automation-conversion/action-templates", json=payload).json()
    replay = client.post("/api/admin/automation-conversion/action-templates", json=payload)

    assert replay.status_code == 201
    body = replay.json()
    assert body["template"]["id"] == created["template"]["id"]
    assert body["idempotent_replay"] is True


def test_create_idempotency_conflict_works(client) -> None:
    payload = {
        "template_name": "Phase 4AE Conflict",
        "template_code": "phase4ae_conflict",
        "idempotency_key": "conflict-key",
        "operator": "pytest",
    }
    client.post("/api/admin/automation-conversion/action-templates", json=payload)

    response = client.post(
        "/api/admin/automation-conversion/action-templates",
        json={**payload, "template_name": "Phase 4AE Conflict Changed"},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "idempotency_conflict"


def test_duplicate_template_code_rejected(client) -> None:
    first = {
        "template_name": "Phase 4AE Duplicate A",
        "template_code": "phase4ae_duplicate",
        "idempotency_key": "dup-a",
        "operator": "pytest",
    }
    second = {
        "template_name": "Phase 4AE Duplicate B",
        "template_code": "phase4ae_duplicate",
        "idempotency_key": "dup-b",
        "operator": "pytest",
    }
    assert client.post("/api/admin/automation-conversion/action-templates", json=first).status_code == 201

    response = client.post("/api/admin/automation-conversion/action-templates", json=second)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_dangerous_fields_rejected(client) -> None:
    response = client.post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "Danger",
            "idempotency_key": "danger-key",
            "default_config": {"workflow_activation": True},
        },
    )

    assert response.status_code == 400
    assert "dangerous action template field" in response.json()["detail"]


def test_audit_event_emitted_and_rollback_payload_present(client) -> None:
    response = client.post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "Phase 4AE Audit",
            "template_code": "phase4ae_audit",
            "idempotency_key": "audit-key",
            "operator": "pytest",
        },
    )

    body = response.json()
    assert body["audit_event"]["operation"] == "create"
    assert body["audit_event"]["resource_type"] == "action_template"
    assert body["rollback_payload"]["created_template_id"] == body["template"]["id"]


def test_side_effect_safety_all_false(client) -> None:
    body = client.get("/api/admin/automation-conversion/action-templates").json()

    assert _all_real_safety_false(body)


def test_production_fixture_post_success_blocked(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.automation_engine.action_template_repository import reset_action_template_fixture_state
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_action_template_fixture_state()
    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "Prod",
            "template_code": "prod",
            "idempotency_key": "prod-key",
            "operator": "pytest",
        },
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"


def test_generate_from_workflow_delete_routes_not_implemented_by_next(client) -> None:
    generate = client.post("/api/admin/automation-conversion/action-templates/generate", json={})
    from_workflow = client.post("/api/admin/automation-conversion/action-templates/from-workflow", json={})
    delete = client.delete("/api/admin/automation-conversion/action-templates/1")

    assert generate.status_code == 404
    assert from_workflow.status_code == 404
    assert delete.status_code == 404


def test_production_compat_main_unchanged() -> None:
    changed, _warnings = checker._changed_files_from_git()

    assert "aicrm_next/main.py" not in changed
    assert "aicrm_next/production_compat/api.py" not in changed


def test_docs_do_not_claim_forbidden_states() -> None:
    text = (ROOT / "docs/development/phase_4ae_action_templates_native_fixture_contract.md").read_text(
        encoding="utf-8"
    ).lower()
    forbidden_patterns = [
        r"production repository enabled",
        r"production write authorized",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text) is None, pattern
