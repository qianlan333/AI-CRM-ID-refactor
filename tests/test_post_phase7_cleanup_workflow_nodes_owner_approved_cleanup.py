from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.check_post_phase7_cleanup_workflow_nodes_owner_approved_cleanup as checker
from aicrm_next.automation_engine.repo import build_automation_repository, reset_automation_fixture_state


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
NATIVE_API = ROOT / "aicrm_next/automation_engine/api.py"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_workflow_nodes_owner_approved_cleanup.yaml"


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_owner_approval_recorded() -> None:
    owner = checker.load_yaml(checker.OWNER_YAML)["owner_approval"]
    assert owner["status"] == "granted"
    assert owner["owner"] == "qianlan"


def test_selected_workflow_nodes_production_compat_removed() -> None:
    text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    assert checker.REMOVED_COMPAT_DECORATOR not in text


def test_unrelated_production_compat_routes_retained() -> None:
    text = PRODUCTION_COMPAT.read_text(encoding="utf-8")
    for route in checker.RETAINED_ROUTES:
        assert route in text


def test_next_native_workflow_nodes_replacement_exists() -> None:
    text = NATIVE_API.read_text(encoding="utf-8")
    for label, pattern in checker.NATIVE_REQUIRED_PATTERNS.items():
        assert __import__("re").search(pattern, text), label


def test_repository_update_and_delete_use_safe_archive_semantics() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    updated = repo.update_workflow_node(1, {"node_name": "Updated node", "metadata": {"source": "pytest"}}, operator="pytest")
    assert updated["node"]["node_name"] == "Updated node"
    assert updated["node"]["metadata"] == {"source": "pytest"}
    assert updated["audit_event"]["operation"] == "update"

    deleted = repo.delete_workflow_node(1, operator="pytest")
    assert deleted["node"]["status"] == "archived"
    assert deleted["node"]["archived_at"]
    assert deleted["hard_delete_executed"] is False
    assert deleted["audit_event"]["operation"] == "archive"

    rows, _total = repo.list_workflow_nodes({"workflow_id": 1, "include_archived": False})
    assert all(item["node_id"] != 1 for item in rows)


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_automation_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_next_native_workflow_node_subpath_routes(client) -> None:
    scoped_list = client.get("/api/admin/automation-conversion/workflows/1/nodes")
    assert scoped_list.status_code == 200
    scoped_body = scoped_list.json()
    assert scoped_body["route_owner"] == "ai_crm_next"
    assert scoped_body["count"] >= 2
    assert all(item["workflow_id"] == 1 for item in scoped_body["items"])
    assert _all_real_safety_false(scoped_body)

    created = client.post(
        "/api/admin/automation-conversion/workflows/4/nodes",
        json={
            "program_id": 4,
            "node_name": "Scoped node",
            "node_code": "scoped_node",
            "node_type": "metadata",
            "idempotency_key": "scoped-node",
            "operator": "pytest",
        },
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["node"]["workflow_id"] == 4
    assert created_body["node"]["node_code"] == "scoped_node"
    assert _all_real_safety_false(created_body)

    node_id = created_body["node"]["node_id"]
    updated = client.put(
        f"/api/admin/automation-conversion/workflow-nodes/{node_id}",
        json={"node_name": "Scoped node updated", "metadata": {"source": "pytest"}, "operator": "pytest"},
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["node"]["node_name"] == "Scoped node updated"
    assert updated_body["audit_event"]["operation"] == "update"
    assert _all_real_safety_false(updated_body)

    deleted = client.delete(f"/api/admin/automation-conversion/workflow-nodes/{node_id}?operator=pytest")
    assert deleted.status_code == 200
    deleted_body = deleted.json()
    assert deleted_body["node"]["status"] == "archived"
    assert deleted_body["hard_delete_executed"] is False
    assert deleted_body["audit_event"]["operation"] == "archive"
    assert _all_real_safety_false(deleted_body)


def test_production_blocked_payload_does_not_report_false_success(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_automation_fixture_state()

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.put(
        "/api/admin/automation-conversion/workflow-nodes/1",
        json={"node_name": "Prod should block", "operator": "pytest"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"
    assert _all_real_safety_false(body)


def test_no_runtime_deletion_claimed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["runtime_deletion_authorized"] is False
    assert data["cleanup_actions"]["runtime_deletion_executed"] is False
    assert data["cleanup_actions"]["wildcard_cleanup_executed"] is False
    assert data["cleanup_actions"]["delete_ready"] is False
    assert data["cleanup_result"]["runtime_deletions_executed"] == []
