from __future__ import annotations

from aicrm_next.channel_entry.application import process_channel_entry
from aicrm_next.channel_entry.schemas import ProcessChannelEntryCommand
from aicrm_next.channel_entry.wecom_adapter import get_wecom_adapter, set_wecom_adapter


def _patch_repo(monkeypatch, *, channel_status="active", bindings=None):
    channel = {"id": 10, "channel_code": "c", "channel_name": "C", "scene_value": "scene-a", "status": channel_status, "owner_staff_id": "sales", "welcome_message": "hello", "entry_tag_id": "tag-a"}
    calls: list[str] = []
    monkeypatch.setattr("aicrm_next.channel_entry.application.resolve_channel_for_scene", lambda **kwargs: (channel, {"match_type": "current_scene", "matched_scene": "scene-a", "channel_id": 10}))
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_contact", lambda **kwargs: calls.append("contact") or {"ok": True})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.get_channel_entry_effect_log", lambda *args: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_entry_effect_log", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.save_tag_snapshot", lambda *args, **kwargs: None)

    class Adapter:
        def send_welcome_msg(self, payload):
            calls.append("welcome")
            return {"errcode": 0}

        def mark_external_contact_tags(self, **payload):
            calls.append("tag")
            return {"errcode": 0}

    previous = get_wecom_adapter()
    set_wecom_adapter(Adapter())
    return calls, previous


def test_active_channel_baseline_emits_only_channel_entry_without_program_admission(monkeypatch):
    calls, previous = _patch_repo(monkeypatch, bindings=[{"id": 20, "program_id": 30, "program_status": "active"}])
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm-a", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["handled"] is True
    assert result["mode"] == "channel_baseline_only"
    assert result["reason"] == "legacy_program_admission_retired"
    assert calls[0] == "contact"
    assert result["welcome_message"]["queued"] is True
    assert result["entry_tag"]["queued"] is True
    assert result["program_member_written"] is False
    assert result["admission_results"] == []
    assert "member" not in calls
    assert "legacy_member" not in calls


def test_archived_program_is_ignored_after_legacy_admission_retirement(monkeypatch):
    calls, previous = _patch_repo(monkeypatch, bindings=[{"id": 20, "program_id": 30, "program_status": "archived"}])
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm-a", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["mode"] == "channel_baseline_only"
    assert result["reason"] == "legacy_program_admission_retired"
    assert result["program_member_written"] is False
    assert result["admission_results"] == []
    assert calls == ["contact"]
    assert result["welcome_message"]["queued"] is True
    assert result["entry_tag"]["queued"] is True
    assert "member" not in calls


def test_channel_disabled_has_no_baseline_side_effects(monkeypatch):
    calls, previous = _patch_repo(monkeypatch, channel_status="inactive")
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm-a", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["handled"] is False
    assert result["mode"] == "channel_disabled"
    assert calls == []
