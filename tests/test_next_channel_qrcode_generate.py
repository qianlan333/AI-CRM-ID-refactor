from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine import channels_api
from aicrm_next.channel_entry.wecom_adapter import set_wecom_adapter
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-qrcode-generate-test")
    channels_api._FIXTURE_CHANNELS.clear()
    channels_api._FIXTURE_PROGRAM_BINDINGS.clear()
    channels_api._NEXT_ID = 1
    channels_api._NEXT_BINDING_ID = 1
    return TestClient(create_app(), raise_server_exceptions=False)


class _Adapter:
    def __init__(self, result: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result or {"errcode": 0, "config_id": "cfg-next-1", "qr_code": "https://wework.qpic.cn/next-generated/1"}

    def create_contact_way(self, payload):
        self.calls.append(payload)
        return self.result


def test_generate_qrcode_calls_next_adapter_and_updates_channel_and_alias(monkeypatch):
    client = _client(monkeypatch)
    adapter = _Adapter()
    set_wecom_adapter(adapter)
    try:
        created = client.post(
            "/api/admin/channels",
            json={
                "channel_name": "Next 真实二维码",
                "channel_code": "next_real_qr",
                "owner_staff_id": "HuangYouCan",
                "welcome_message": "欢迎",
            },
        ).json()["channel"]

        response = client.post(f"/api/admin/channels/{created['id']}/qrcode/generate", json={"force_new_scene": True})

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "aicrm_next.channel_entry"
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["config_id"] == "cfg-next-1"
        assert payload["qr_url"] == "https://wework.qpic.cn/next-generated/1"
        assert payload["alias_id"] > 0
        assert payload["scene_value"].startswith("aqr_")
        assert adapter.calls == [{"type": 2, "scene": 2, "state": payload["scene_value"], "user": ["HuangYouCan"]}]

        detail = client.get(f"/api/admin/channels/{created['id']}").json()["channel"]
        assert detail["scene_value"] == payload["scene_value"]
        assert detail["qr_url"] == payload["qr_url"]

        download = client.get(f"/api/admin/channels/{created['id']}/qrcode/download", follow_redirects=False)
        assert download.status_code == 302
        assert download.headers["location"] == payload["qr_url"]
    finally:
        set_wecom_adapter(None)


def test_generate_qrcode_does_not_fake_success_when_real_calls_disabled(monkeypatch):
    client = _client(monkeypatch)
    set_wecom_adapter(None)
    monkeypatch.setenv("WECOM_CORP_ID", "ww-real")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret-real")
    monkeypatch.setenv("WECOM_CALLBACK_TOKEN", "token")
    monkeypatch.setenv("WECOM_CALLBACK_AES_KEY", "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG")

    created = client.post(
        "/api/admin/channels",
        json={"channel_name": "未开启真实调用二维码", "channel_code": "next_blocked_qr", "owner_staff_id": "HuangYouCan"},
    ).json()["channel"]

    response = client.post(f"/api/admin/channels/{created['id']}/qrcode/generate", json={"scene_value": "aqr_blocked"})

    assert response.status_code == 503
    assert response.json()["reason"] == "wecom_real_calls_disabled"
    detail = client.get(f"/api/admin/channels/{created['id']}").json()["channel"]
    assert detail["qr_url"] == ""
