from __future__ import annotations

from aicrm_next.channel_entry.application import process_channel_entry
from aicrm_next.channel_entry.schemas import ProcessChannelEntryCommand
from aicrm_next.channel_entry.wecom_adapter import set_wecom_adapter


class _Runtime:
    def __init__(self) -> None:
        self.channel = {
            "id": 7,
            "channel_code": "next_contract",
            "channel_name": "Next contract",
            "scene_value": "scene-contract",
            "status": "active",
            "owner_staff_id": "owner-contract",
            "welcome_message": "欢迎进入",
            "entry_tag_id": "tag-contract",
            "entry_tag_name": "合同标签",
            "carrier_type": "qrcode",
        }
        self.effects: list[dict] = []
        self.welcome_calls: list[dict] = []
        self.tag_calls: list[dict] = []

    def install(self, monkeypatch):
        monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_value", lambda scene: self.channel if scene == "scene-contract" else None)
        monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_alias", lambda corp_id, scene: None)
        monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_historical_scene_value", lambda scene: None)
        monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_scene_alias", lambda **kwargs: kwargs)
        monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_contact", lambda **kwargs: {"id": 1, **kwargs})
        monkeypatch.setattr("aicrm_next.channel_entry.repo.get_channel_entry_effect_log", lambda effect_type, idempotency_key: None)
        monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_entry_effect_log", self._effect)
        monkeypatch.setattr("aicrm_next.channel_entry.repo.list_active_bindings_for_channel", lambda channel_id: [])
        monkeypatch.setattr("aicrm_next.channel_entry.repo.save_tag_snapshot", lambda *args, **kwargs: None)

        runtime = self

        class Adapter:
            def send_welcome_msg(self, payload):
                runtime.welcome_calls.append(payload)
                return {"errcode": 0, "errmsg": "ok"}

            def mark_external_contact_tags(self, **payload):
                runtime.tag_calls.append(payload)
                return {"errcode": 0, "errmsg": "ok"}

        set_wecom_adapter(Adapter())

    def _effect(self, **kwargs):
        self.effects.append(kwargs)
        return {"id": len(self.effects), **kwargs}


def test_callback_uses_next_adapter_for_welcome_and_entry_tag(monkeypatch):
    runtime = _Runtime()
    runtime.install(monkeypatch)
    try:
        result = process_channel_entry(
            ProcessChannelEntryCommand(
                external_contact_id="wm-contract",
                follow_user_userid="owner-contract",
                payload_json={"State": "scene-contract", "WelcomeCode": "welcome-contract", "corp_id": "ww-contract"},
                send_welcome_message=True,
                event_log_id=7001,
            )
        )
    finally:
        set_wecom_adapter(None)

    assert result["handled"] is True
    assert result["welcome_message"]["sent"] is True
    assert result["entry_tag"]["applied"] is True
    assert runtime.welcome_calls == [{"welcome_code": "welcome-contract", "text": {"content": "欢迎进入"}}]
    assert runtime.tag_calls == [
        {
            "external_userid": "wm-contract",
            "follow_user_userid": "owner-contract",
            "add_tags": ["tag-contract"],
            "remove_tags": [],
        }
    ]
    assert any(row["effect_type"] == "welcome_message" and row["status"] == "success" for row in runtime.effects)
    assert any(row["effect_type"] == "entry_tag" and row["status"] == "success" for row in runtime.effects)
