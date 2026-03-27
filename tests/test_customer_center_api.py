from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test.sqlite3"
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
            "SIDEBAR_PERSON_DETAIL_URL_TEMPLATE": "https://www.youcangogogo.com/person/{person_id}",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def seed_customer_fixture(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            ("sales_01", "顾问一号", "sales", 1, "sales_02", "顾问二号", "sales", 1),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_customer_001",
                "客户甲",
                "sales_01",
                "重点客户",
                "客户甲描述",
                "2026-03-24 10:00:00",
                "wm_customer_002",
                "客户乙",
                "sales_02",
                "未绑定客户",
                "客户乙描述",
                "2026-03-24 09:00:00",
            ),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13900000001", "tp_001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13900000001",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_customer_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_customer_001",
                "union-001",
                "openid-001",
                "sales_01",
                "客户甲",
                "active",
                "{}",
                "ww-test",
                "wm_customer_002",
                "union-002",
                "openid-002",
                "sales_02",
                "客户乙",
                "active",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_customer_001",
                "sales_01",
                "active",
                1,
                "备注甲",
                "描述甲",
                "{}",
                "ww-test",
                "wm_customer_002",
                "sales_02",
                "active",
                1,
                "备注乙",
                "描述乙",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
            VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
            """,
            (
                "wm_customer_001",
                "sales_01",
                "tag-vip",
                "高意向",
                "2026-03-24 10:00:00",
                "wm_customer_002",
                "sales_02",
                "tag-cold",
                "待跟进",
                "2026-03-24 09:30:00",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_customer_001", "signed_999", "已报名999", "客户甲", "sales_01", "13900000001", "sales_01", "success", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "msg-001",
                "wm_customer_001",
                "sales_01",
                "sales_01",
                "wm_customer_001",
                "text",
                "你好",
                "2026-03-24 11:00:00",
                "{}",
                2,
                "msg-002",
                "wm_customer_002",
                "sales_02",
                "sales_02",
                "wm_customer_002",
                "text",
                "稍后联系",
                "2026-03-24 12:00:00",
                "{}",
            ),
        )
        db.commit()


def test_customers_list_returns_aggregated_results(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"limit": 10, "offset": 0})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["count"] == 2
    assert len(payload["customers"]) == 2
    assert payload["filters"] == {
        "owner_userid": "",
        "tag": "",
        "status": "",
        "is_bound": "",
        "mobile": "",
        "keyword": "",
        "limit": "10",
        "offset": "0",
    }
    assert {item["external_userid"] for item in payload["customers"]} == {"wm_customer_001", "wm_customer_002"}


def test_customers_list_filters_by_owner_userid(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"owner_userid": "sales_01"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["owner_userid"] == "sales_01"


def test_customers_list_filters_by_is_bound(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"is_bound": "false"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["external_userid"] == "wm_customer_002"
    assert payload["customers"][0]["is_bound"] is False


def test_customer_detail_returns_unified_dto(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers/wm_customer_001")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    customer = payload["customer"]
    assert customer["external_userid"] == "wm_customer_001"
    assert customer["customer_name"] == "客户甲"
    assert customer["owner_userid"] == "sales_01"
    assert customer["mobile"] == "13900000001"
    assert customer["binding_status"] == "bound"
    assert customer["follow_user_userids"] == ["sales_01"]
    assert customer["class_user_status"]["signup_status"] == "signed_999"
    assert customer["last_message_at"] == "2026-03-24 11:00:00"
    assert customer["last_touch_at"] == "2026-03-24 11:00:00"


def test_legacy_contacts_api_smoke_still_works(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/contacts", query_string={"sync": "0", "owner_userid": "sales_01"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "contacts" in payload
