from __future__ import annotations

from aicrm_next.channel_entry.application import resolve_channel_for_scene


def test_current_scene_upserts_alias(monkeypatch):
    calls = []
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_value", lambda scene: {"id": 1, "scene_value": scene, "qr_url": "qr", "carrier_type": "qrcode"})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_scene_alias", lambda **kwargs: calls.append(kwargs) or {"id": 5})

    channel, match = resolve_channel_for_scene(scene_value="scene-current", corp_id="ww")

    assert channel["id"] == 1
    assert match["match_type"] == "current_scene"
    assert calls[0]["scene_value"] == "scene-current"


def test_scene_alias_resolves_before_historical_vote(monkeypatch):
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_value", lambda scene: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_alias", lambda corp_id, scene: {"id": 2, "scene_alias_id": 9, "scene_alias_status": "active", "scene_alias_source": "channel_save_current_scene"})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.update_alias_last_seen_at", lambda corp_id, scene: 1)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_historical_scene_value", lambda scene: (_ for _ in ()).throw(AssertionError("historical vote should not be primary")))

    channel, match = resolve_channel_for_scene(scene_value="scene-old", corp_id="ww")

    assert channel["id"] == 2
    assert match["match_type"] == "scene_alias"


def test_historical_vote_backfills_alias(monkeypatch):
    calls = []
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_value", lambda scene: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_scene_alias", lambda corp_id, scene: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.find_channel_by_historical_scene_value", lambda scene: {"id": 3, "scene_value": "scene-new"})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.backfill_scene_alias_from_historical_vote", lambda scene, channel_id: calls.append((scene, channel_id)) or {"id": 10, "channel_id": channel_id, "source": "historical_backfill"})

    channel, match = resolve_channel_for_scene(scene_value="scene-old", corp_id="ww")

    assert channel["id"] == 3
    assert match["match_type"] == "historical_vote"
    assert calls == [("scene-old", 3)]

