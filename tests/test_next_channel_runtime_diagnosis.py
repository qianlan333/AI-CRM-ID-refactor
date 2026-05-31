from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_runtime_diagnosis_route_is_next_native(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr("aicrm_next.channel_entry.api.diagnose_channel_runtime", lambda query: {"ok": True, "callback_route_owner": "aicrm_next.channel_entry", "scene": query.scene_value})

    response = TestClient(create_app(), raise_server_exceptions=False).get("/api/admin/channels/runtime-diagnosis?scene_value=s1")

    assert response.status_code == 200
    assert response.json()["callback_route_owner"] == "aicrm_next.channel_entry"


def test_dry_run_and_repair_routes_are_next_native(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr("aicrm_next.channel_entry.api.dry_run_channel_entry", lambda command: {"dry_run": True, "would_actions": {}, "external": command.external_contact_id})
    monkeypatch.setattr("aicrm_next.channel_entry.api.repair_channel_entry", lambda command: {"handled": True, "welcome_repair": {"reason": "welcome_code_unavailable_or_expired"}})
    client = TestClient(create_app(), raise_server_exceptions=False)

    dry = client.post("/api/admin/channels/runtime-diagnosis/dry-run", json={"external_userid": "wm", "scene_value": "s1"})
    repair = client.post("/api/admin/channels/repair-entry", json={"external_userid": "wm", "scene_value": "s1"})

    assert dry.status_code == 200
    assert dry.json()["planned_actions"]["dry_run"] is True
    assert repair.status_code == 200
    assert repair.json()["source"] == "aicrm_next.channel_entry"

