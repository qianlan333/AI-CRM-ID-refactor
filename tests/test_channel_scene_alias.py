from __future__ import annotations

import json

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import repo
from wecom_ability_service.domains.automation_conversion.member_state_service import handle_channel_enter_from_callback

from automation_channel_admission_helpers import create_channel, create_program


def test_save_channel_preserves_previous_scene_as_alias(app):
    with app.app_context():
        first = repo.save_channel(
            {
                "channel_code": "default_qrcode",
                "channel_name": "默认渠道二维码",
                "scene_value": "scene_alias_first",
                "owner_staff_id": "HuangYouCan",
                "status": "active",
            }
        )
        second = repo.save_channel(
            {
                "channel_code": "default_qrcode",
                "channel_name": "默认渠道二维码",
                "scene_value": "scene_alias_second",
                "owner_staff_id": "HuangYouCan",
                "status": "active",
            }
        )
        get_db().commit()

        aliases = repo.get_channel_scene_aliases(int(second["id"]))
        scenes = {item["scene_value"] for item in aliases}
        assert first["id"] == second["id"]
        assert {"scene_alias_first", "scene_alias_second"} <= scenes


def test_historical_scene_alias_resolves_without_historical_vote(app):
    with app.app_context():
        create_program("scene_alias_program")
        channel = create_channel("scene_alias_channel")
        old_scene = str(channel["scene_value"])
        get_db().execute(
            "UPDATE automation_channel SET scene_value = 'scene_alias_current' WHERE id = ?",
            (int(channel["id"]),),
        )
        get_db().commit()

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_scene_alias",
            payload_json={"State": old_scene},
            follow_user_userid="HuangYouCan",
        )

        assert result["handled"] is True
        assert result["scene_match"]["match_type"] == "scene_alias"
        assert result["channel"]["id"] == int(channel["id"])


def test_historical_vote_fallback_backfills_scene_alias(app):
    with app.app_context():
        create_program("historical_vote_program")
        channel = create_channel("historical_vote_channel")
        old_scene = "scene_historical_vote_old"
        get_db().execute("DELETE FROM automation_channel_scene_alias WHERE channel_id = ?", (int(channel["id"]),))
        get_db().execute(
            "UPDATE automation_channel SET scene_value = 'scene_historical_vote_current' WHERE id = ?",
            (int(channel["id"]),),
        )
        get_db().execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool,
                questionnaire_status, decision_source, source_type, source_channel_id,
                created_at, updated_at
            )
            VALUES ('wm_scene_vote_history', '', 'HuangYouCan', TRUE, 'pending_questionnaire',
                'pending', 'system', 'qrcode', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (int(channel["id"]),),
        )
        get_db().execute(
            """
            INSERT INTO wecom_external_contact_event_logs (
                corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
                payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
            )
            VALUES (
                'ww-test', 'change_external_contact', 'add_external_contact',
                'wm_scene_vote_history', 'HuangYouCan', 1712023200, 'event-historical-vote',
                '<xml></xml>', CAST(? AS jsonb), 'success', 0, '',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (json.dumps({"State": old_scene}),),
        )
        get_db().commit()

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_scene_vote_future",
            payload_json={"State": old_scene},
            follow_user_userid="HuangYouCan",
        )

        assert result["handled"] is True
        assert result["scene_match"]["match_type"] == "historical_vote"
        alias = repo.find_channel_by_scene_alias("", old_scene)
        assert alias is not None
        assert alias["scene_alias_source"] == "historical_backfill"
        assert int(alias["id"]) == int(channel["id"])
