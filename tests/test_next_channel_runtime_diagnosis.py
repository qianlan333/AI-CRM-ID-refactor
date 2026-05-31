from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.channel_entry.application import diagnose_channel_runtime
from aicrm_next.channel_entry.schemas import DiagnoseChannelRuntimeQuery
from aicrm_next.channel_entry.wecom_adapter import set_wecom_adapter
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


def test_runtime_diagnosis_reports_real_adapter_capabilities(monkeypatch):
    set_wecom_adapter(None)
    monkeypatch.setenv("WECOM_CORP_ID", "ww-real")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret-real")
    monkeypatch.setenv("WECOM_CALLBACK_TOKEN", "token")
    monkeypatch.setenv("WECOM_CALLBACK_AES_KEY", "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG")
    monkeypatch.delenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", raising=False)
    channel = {
        "id": 1,
        "scene_value": "s1",
        "status": "active",
        "welcome_message": "欢迎",
        "entry_tag_id": "tag-1",
        "carrier_type": "qrcode",
    }
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_value", lambda scene: channel)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_alias", lambda corp_id, scene: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_historical_scene_value", lambda scene: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_channel_scene_aliases", lambda channel_id: [])
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_active_bindings_for_channel", lambda channel_id: [])
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_channel_entry_effect_logs", lambda **kwargs: [])
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_recent_events", lambda scene, limit=20: [])

    diagnosis = diagnose_channel_runtime(DiagnoseChannelRuntimeQuery(scene_value="s1"))

    assert diagnosis["real_wecom_adapter_enabled"] is False
    assert diagnosis["real_wecom_adapter_reason"] == "real_calls_disabled"
    assert diagnosis["can_send_welcome"] is False
    assert diagnosis["can_mark_tag"] is False
    assert diagnosis["can_create_contact_way"] is False
    assert diagnosis["adapter_warnings"]["welcome_message"] == "当前不会真实发欢迎语"
    assert diagnosis["adapter_warnings"]["entry_tag"] == "当前不会真实打标签"
    assert diagnosis["adapter_warnings"]["qrcode_generate"] == "当前不会真实生成二维码"
