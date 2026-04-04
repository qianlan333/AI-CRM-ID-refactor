from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import evaluate_customer_marketing_state, evaluate_customer_value_segment


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "marketing-state.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        init_db()
    yield app


def _seed_person(app, *, person_id: int, mobile: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (person_id, mobile, f"tp-{person_id}"),
        )
        db.commit()


def _seed_bound_external(
    app,
    *,
    person_id: int,
    external_userid: str,
    mobile: str,
    customer_name: str,
    owner_userid: str = "sales_01",
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, person_id, owner_userid, owner_userid, owner_userid),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO owner_role_map (userid, display_name, role, active, updated_at)
            VALUES (?, ?, 'sales', 1, CURRENT_TIMESTAMP)
            """,
            (owner_userid, owner_userid),
        )
        db.execute(
            """
            UPDATE people
            SET mobile = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (mobile, person_id),
        )
        db.commit()


def _seed_class_user_status(
    app,
    *,
    external_userid: str,
    mobile: str,
    owner_userid: str,
    customer_name: str,
    signup_status: str,
    signup_label_name: str,
    set_at: str,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'success', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, signup_status, signup_label_name, customer_name, owner_userid, mobile, owner_userid, set_at),
        )
        db.commit()


def _seed_lead_pool_activation(
    app,
    *,
    mobile: str,
    external_userid: str,
    customer_name: str,
    owner_userid: str,
    activation_state: str,
    updated_at: str,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
                huangxiaocan_activation_state, class_term_no, class_term_label, first_entry_source,
                last_entry_source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, 1, ?, NULL, '', 'seed', 'seed', ?, ?)
            """,
            (mobile, external_userid, customer_name, owner_userid, activation_state, updated_at, updated_at),
        )
        db.commit()


def _seed_activation_source(app, *, mobile: str, activation_state: str, updated_at: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_huangxiaocan_activation_source (
                mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, ?, 'batch-seed', 'seed', 1, ?, ?)
            """,
            (mobile, activation_state, updated_at, updated_at),
        )
        db.commit()


def _seed_message(
    app,
    *,
    external_userid: str,
    owner_userid: str,
    send_time: str,
    sender: str | None = None,
):
    message_sender = sender or external_userid
    receiver = owner_userid if message_sender == external_userid else external_userid
    with app.app_context():
        db = get_db()
        sequence = int(
            db.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM archived_messages").fetchone()["next_seq"]
        )
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, 'private', ?, ?, ?, ?, 'text', 'hello', ?, '{}')
            """,
            (sequence, f"{external_userid}-{sequence}", external_userid, owner_userid, message_sender, receiver, send_time),
        )
        db.commit()


def test_marketing_state_service_covers_all_stages_and_priorities(app):
    _seed_person(app, person_id=401, mobile="13800138401")
    _seed_person(app, person_id=402, mobile="13800138402")
    _seed_person(app, person_id=403, mobile="13800138403")
    _seed_person(app, person_id=404, mobile="13800138404")

    _seed_bound_external(
        app,
        person_id=402,
        external_userid="wm_ms_wecom",
        mobile="13800138402",
        customer_name="企微已连接客户",
    )
    _seed_bound_external(
        app,
        person_id=403,
        external_userid="wm_ms_activated",
        mobile="13800138403",
        customer_name="已激活客户",
    )
    _seed_bound_external(
        app,
        person_id=404,
        external_userid="wm_ms_converted",
        mobile="13800138404",
        customer_name="已转化客户",
    )
    _seed_lead_pool_activation(
        app,
        mobile="13800138403",
        external_userid="wm_ms_activated",
        customer_name="已激活客户",
        owner_userid="sales_01",
        activation_state="activated",
        updated_at="2026-04-04 09:00:00",
    )
    _seed_lead_pool_activation(
        app,
        mobile="13800138404",
        external_userid="wm_ms_converted",
        customer_name="已转化客户",
        owner_userid="sales_01",
        activation_state="activated",
        updated_at="2026-04-04 09:05:00",
    )
    _seed_class_user_status(
        app,
        external_userid="wm_ms_converted",
        mobile="13800138404",
        owner_userid="sales_01",
        customer_name="已转化客户",
        signup_status="signed_999",
        signup_label_name="已报名999",
        set_at="2026-04-04 10:00:00",
    )
    _seed_message(app, external_userid="wm_ms_activated", owner_userid="sales_01", send_time="2026-04-04 08:40:00")
    _seed_message(app, external_userid="wm_ms_converted", owner_userid="sales_01", send_time="2026-04-04 09:50:00")

    with app.app_context():
        mobile_only = evaluate_customer_marketing_state(person_id=401)
        wecom_connected = evaluate_customer_marketing_state(person_id=402)
        activated = evaluate_customer_marketing_state(external_userid="wm_ms_activated")
        converted = evaluate_customer_marketing_state(person_id=404)

        assert mobile_only["stage_key"] == "prospect/mobile_only"
        assert mobile_only["eligible_for_conversion"] is False
        assert mobile_only["external_userid"] == ""

        assert wecom_connected["stage_key"] == "prospect/wecom_connected"
        assert wecom_connected["eligible_for_conversion"] is True
        assert wecom_connected["activated"] is False
        assert wecom_connected["converted"] is False

        assert activated["stage_key"] == "active/activated"
        assert activated["eligible_for_conversion"] is True
        assert activated["activated"] is True
        assert activated["last_activation_at"] == "2026-04-04 09:00:00"
        assert activated["last_message_at"] == "2026-04-04 08:40:00"

        assert converted["stage_key"] == "converted/enrolled"
        assert converted["eligible_for_conversion"] is False
        assert converted["activated"] is True
        assert converted["converted"] is True
        assert converted["exit_reason"] == "enrolled"
        assert converted["last_conversion_marked_at"] == "2026-04-04 10:00:00"

        current_rows = get_db().execute(
            """
            SELECT person_id, external_userid, main_stage, sub_stage, activated, converted, eligible_for_conversion, exit_reason, last_message_at
            FROM customer_marketing_state_current
            ORDER BY person_id ASC
            """
        ).fetchall()
        assert len(current_rows) == 4
        assert current_rows[0]["external_userid"] == ""
        assert current_rows[0]["sub_stage"] == "mobile_only"
        assert bool(current_rows[3]["converted"]) is True
        assert bool(current_rows[3]["eligible_for_conversion"]) is False
        assert current_rows[3]["exit_reason"] == "enrolled"
        assert current_rows[3]["last_message_at"] == "2026-04-04 09:50:00"

        history_rows = get_db().execute(
            """
            SELECT external_userid, sub_stage
            FROM customer_marketing_state_history
            WHERE person_id = ?
            ORDER BY id ASC
            """,
            (401,),
        ).fetchall()
        assert [dict(row) for row in history_rows] == [{"external_userid": "", "sub_stage": "mobile_only"}]


def test_marketing_state_service_does_not_append_history_without_change(app):
    _seed_person(app, person_id=501, mobile="13800138501")
    _seed_bound_external(
        app,
        person_id=501,
        external_userid="wm_ms_repeat",
        mobile="13800138501",
        customer_name="重复计算客户",
    )

    with app.app_context():
        first = evaluate_customer_marketing_state(person_id=501)
        assert first["stage_key"] == "prospect/wecom_connected"

        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_marketing_state_history WHERE person_id = ?",
            (501,),
        ).fetchone()["total"]
        assert history_total == 1

        second = evaluate_customer_marketing_state(external_userid="wm_ms_repeat")
        assert second["stage_key"] == "prospect/wecom_connected"

        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_marketing_state_history WHERE person_id = ?",
            (501,),
        ).fetchone()["total"]
        assert history_total == 1

    _seed_activation_source(
        app,
        mobile="13800138501",
        activation_state="activated",
        updated_at="2026-04-04 12:00:00",
    )

    with app.app_context():
        third = evaluate_customer_marketing_state(person_id=501)
        assert third["stage_key"] == "active/activated"
        assert third["last_activation_at"] == "2026-04-04 12:00:00"

        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_marketing_state_history WHERE person_id = ?",
            (501,),
        ).fetchone()["total"]
        assert history_total == 2


def test_mobile_only_people_can_coexist_without_fake_external_userid_and_value_segment_errors(app):
    _seed_person(app, person_id=601, mobile="13800138601")
    _seed_person(app, person_id=602, mobile="13800138602")

    with app.app_context():
        first_state = evaluate_customer_marketing_state(person_id=601)
        second_state = evaluate_customer_marketing_state(person_id=602)
        first_segment = evaluate_customer_value_segment(person_id=601)
        second_segment = evaluate_customer_value_segment(person_id=602)

        assert first_state["stage_key"] == "prospect/mobile_only"
        assert second_state["stage_key"] == "prospect/mobile_only"
        assert first_state["external_userid"] == ""
        assert second_state["external_userid"] == ""
        assert first_segment["segment"] == "unknown"
        assert second_segment["segment"] == "unknown"

        rows = get_db().execute(
            """
            SELECT person_id, external_userid
            FROM customer_marketing_state_current
            WHERE person_id IN (?, ?)
            ORDER BY person_id ASC
            """,
            (601, 602),
        ).fetchall()
        assert [dict(row) for row in rows] == [
            {"person_id": 601, "external_userid": ""},
            {"person_id": 602, "external_userid": ""},
        ]
