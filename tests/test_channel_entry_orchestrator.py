from __future__ import annotations

import json

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import repo, service as automation_service
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program
from wecom_ability_service.domains.automation_conversion.member_state_service import handle_channel_enter_from_callback

from automation_channel_admission_helpers import (
    create_channel,
    create_program,
    disabled_entry_rule,
    fetch_channel_contact,
    fetch_program_member,
    save_audience_entry_rule,
    table_count,
)


def _configure_channel(channel_id: int) -> None:
    get_db().execute(
        """
        UPDATE automation_channel
        SET welcome_message = '欢迎加入报名渠道',
            entry_tag_id = 'tag-signup-lead',
            entry_tag_name = '报名引流品',
            entry_tag_group_name = '来源',
            owner_staff_id = 'HuangYouCan',
            status = 'active'
        WHERE id = ?
        """,
        (int(channel_id),),
    )
    get_db().commit()


def _stub_wecom(monkeypatch):
    sent: dict[str, list[dict[str, object]]] = {"welcome": [], "tag": []}

    class _ContactClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            sent["welcome"].append(payload)
            return {"errcode": 0, "errmsg": "ok"}

    class _AppClient:
        def mark_external_contact_tags(
            self,
            *,
            external_userid: str,
            follow_user_userid: str,
            add_tags: list[str],
            remove_tags: list[str],
        ) -> dict[str, object]:
            sent["tag"].append(
                {
                    "external_userid": external_userid,
                    "follow_user_userid": follow_user_userid,
                    "add_tags": list(add_tags),
                    "remove_tags": list(remove_tags),
                }
            )
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(automation_service, "get_contact_runtime_client", lambda: _ContactClient())
    monkeypatch.setattr(automation_service, "get_app_runtime_client", lambda: _AppClient())
    return sent


def test_current_scene_active_channel_runs_baseline_then_program_admission(app, monkeypatch):
    sent = _stub_wecom(monkeypatch)

    with app.app_context():
        program_id = create_program("channel_entry_current")
        channel = create_channel("channel_entry_current")
        _configure_channel(int(channel["id"]))
        bind_channels_to_program(program_id, [int(channel["id"])], {}, "pytest")
        save_audience_entry_rule(program_id, disabled_entry_rule())

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_channel_entry_current",
            payload_json={"State": channel["scene_value"], "WelcomeCode": "welcome-current"},
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["mode"] == "program_admission"
        assert result["scene_match"]["match_type"] == "current_scene"
        assert result["baseline_effects"]["welcome_message"]["sent"] is True
        assert result["baseline_effects"]["entry_tag"]["applied"] is True
        assert fetch_channel_contact(int(channel["id"]), "wm_channel_entry_current") is not None
        assert fetch_program_member("wm_channel_entry_current", program_id) is not None
        assert sent["welcome"] == [{"welcome_code": "welcome-current", "text": {"content": "欢迎加入报名渠道"}}]
        assert sent["tag"] == [
            {
                "external_userid": "wm_channel_entry_current",
                "follow_user_userid": "HuangYouCan",
                "add_tags": ["tag-signup-lead"],
                "remove_tags": [],
            }
        ]
        assert table_count("automation_channel_entry_effect_log", "channel_id = ?", (int(channel["id"]),)) >= 4


def test_archived_program_keeps_channel_baseline_without_program_member(app, monkeypatch):
    sent = _stub_wecom(monkeypatch)

    with app.app_context():
        program_id = create_program("channel_entry_archived", status="archived")
        channel = create_channel("channel_entry_archived")
        _configure_channel(int(channel["id"]))
        bind_channels_to_program(program_id, [int(channel["id"])], {}, "pytest")

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_channel_entry_archived",
            payload_json={"State": channel["scene_value"], "WelcomeCode": "welcome-archived"},
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["mode"] == "channel_baseline_only"
        assert result["reason"] == "program_archived"
        assert result["program_member_written"] is False
        assert result["welcome_message"]["sent"] is True
        assert result["entry_tag"]["applied"] is True
        assert fetch_channel_contact(int(channel["id"]), "wm_channel_entry_archived") is not None
        assert fetch_program_member("wm_channel_entry_archived", program_id) is None
        assert result["admission_results"][0]["admission_status"] == "rejected"
        assert result["admission_results"][0]["reason"] == "program_archived"
        assert len(sent["welcome"]) == 1
        assert len(sent["tag"]) == 1


def test_no_active_binding_runs_standalone_channel_baseline(app, monkeypatch):
    sent = _stub_wecom(monkeypatch)

    with app.app_context():
        create_program("channel_entry_standalone_program")
        channel = create_channel("channel_entry_standalone")
        _configure_channel(int(channel["id"]))

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_channel_entry_standalone",
            payload_json={"State": channel["scene_value"], "WelcomeCode": "welcome-standalone"},
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["mode"] == "standalone_channel"
        assert result["program_member_written"] is False
        assert result["welcome_message"]["sent"] is True
        assert result["entry_tag"]["applied"] is True
        assert sent["welcome"][0]["welcome_code"] == "welcome-standalone"
        assert fetch_channel_contact(int(channel["id"]), "wm_channel_entry_standalone") is not None


def test_channel_disabled_does_not_run_baseline_effects(app, monkeypatch):
    sent = _stub_wecom(monkeypatch)

    with app.app_context():
        channel = create_channel("channel_entry_disabled", status="inactive")
        _configure_channel(int(channel["id"]))
        get_db().execute("UPDATE automation_channel SET status = 'inactive' WHERE id = ?", (int(channel["id"]),))
        get_db().commit()

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_channel_entry_disabled",
            payload_json={"State": channel["scene_value"], "WelcomeCode": "welcome-disabled"},
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )

        assert result["handled"] is False
        assert result["mode"] == "channel_disabled"
        assert result["reason"] == "channel_disabled"
        assert sent["welcome"] == []
        assert sent["tag"] == []
        assert fetch_channel_contact(int(channel["id"]), "wm_channel_entry_disabled") is None


def test_duplicate_effects_are_idempotent_by_welcome_code_and_tag(app, monkeypatch):
    sent = _stub_wecom(monkeypatch)

    with app.app_context():
        create_program("channel_entry_idempotent_program")
        channel = create_channel("channel_entry_idempotent")
        _configure_channel(int(channel["id"]))
        payload = {"State": channel["scene_value"], "WelcomeCode": "welcome-idempotent"}

        first = handle_channel_enter_from_callback(
            external_contact_id="wm_channel_entry_idempotent",
            payload_json=payload,
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )
        second = handle_channel_enter_from_callback(
            external_contact_id="wm_channel_entry_idempotent",
            payload_json=payload,
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )

        assert first["welcome_message"]["sent"] is True
        assert first["entry_tag"]["applied"] is True
        assert second["welcome_message"]["reason"] == "idempotent_success_exists"
        assert second["entry_tag"]["reason"] == "idempotent_success_exists"
        assert len(sent["welcome"]) == 1
        assert len(sent["tag"]) == 1
        assert table_count("automation_channel_entry_effect_log", "effect_type = 'welcome_message' AND status = 'success'") == 1
        assert table_count("automation_channel_entry_effect_log", "effect_type = 'entry_tag' AND status = 'success'") == 1


def test_worker_process_external_contact_event_runs_channel_entry_baseline(app, monkeypatch):
    sent = _stub_wecom(monkeypatch)

    class _ContactDetailClient:
        def get_contact(self, external_userid: str) -> dict[str, object]:
            return {"external_userid": external_userid, "follow_user": []}

    monkeypatch.setattr("wecom_ability_service.routes._contact_client", lambda: _ContactDetailClient())
    monkeypatch.setattr(
        "wecom_ability_service.http.background_jobs._sync_contact_detail_with_description_fix",
        lambda client, detail, **kwargs: ({"external_userid": detail["external_userid"], "mobile": "13800000001", "owner_userid": "HuangYouCan"}, {}),
    )
    monkeypatch.setattr("wecom_ability_service.http.background_jobs.upsert_contacts", lambda rows: None)
    monkeypatch.setattr("wecom_ability_service.http.background_jobs._upsert_external_contact_identity", lambda record: 1)
    monkeypatch.setattr("wecom_ability_service.http.background_jobs._replace_external_contact_follow_users", lambda **kwargs: None)
    monkeypatch.setattr("wecom_ability_service.http.background_jobs._refresh_external_contact_identity_owner", lambda **kwargs: None)
    monkeypatch.setattr(
        "wecom_ability_service.http.background_jobs.ScheduleUserOpsAutoAssignClassTermJobCommand",
        lambda: (lambda dto: {"scheduled": False}),
    )

    with app.app_context():
        create_program("worker_channel_entry_program")
        channel = create_channel("worker_channel_entry")
        _configure_channel(int(channel["id"]))
        event_id = int(
            get_db().execute(
                """
                INSERT INTO wecom_external_contact_event_logs (
                    corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
                    payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
                )
                VALUES (
                    'ww-test', 'change_external_contact', 'add_external_contact',
                    'wm_worker_channel_entry', 'HuangYouCan', 1712023200, 'event-worker-channel-entry',
                    '<xml></xml>', CAST(? AS jsonb), 'pending', 0, '',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING id
                """,
                (json.dumps({"State": channel["scene_value"], "WelcomeCode": "welcome-worker"}),),
            ).fetchone()["id"]
        )
        get_db().commit()

        from wecom_ability_service.http.background_jobs import _process_external_contact_event

        result = _process_external_contact_event(event_id)

        assert result["ok"] is True
        assert fetch_channel_contact(int(channel["id"]), "wm_worker_channel_entry") is not None
        assert sent["welcome"] == [{"welcome_code": "welcome-worker", "text": {"content": "欢迎加入报名渠道"}}]
        assert sent["tag"][0]["external_userid"] == "wm_worker_channel_entry"
        assert table_count("automation_channel_entry_effect_log", "event_log_id = ?", (event_id,)) >= 4
