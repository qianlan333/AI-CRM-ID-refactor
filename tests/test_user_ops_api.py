from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from aicrm_next.main import create_app
from aicrm_next.ops_enrollment.application import reset_user_ops_fixture_state
from aicrm_next.shared.db_session import get_session_factory


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_user_ops_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False


def test_user_ops_read_routes_use_next_fixtures(monkeypatch):
    client = _client(monkeypatch)

    overview = client.get("/api/admin/user-ops/overview")
    cards = client.get("/api/admin/user-ops/cards")
    filters = client.get("/api/admin/user-ops/filters")
    customers = client.get("/api/admin/user-ops/customers?limit=5")

    for response in (overview, cards, filters, customers):
        assert response.status_code == 200
        _assert_next(response.json())
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"

    assert overview.json()["cards"]
    assert cards.json()["cards"]
    assert filters.json()["filter_options"]["wecom_status"]
    assert customers.json()["items"]


def test_user_ops_customer_detail_and_timeline_are_next_owned(monkeypatch):
    client = _client(monkeypatch)
    first = client.get("/api/admin/user-ops/customers?limit=1").json()["items"][0]
    unionid = first["unionid"]

    detail = client.get(f"/api/admin/user-ops/customers/{unionid}")
    timeline = client.get(f"/api/admin/user-ops/customers/{unionid}/timeline")

    for response in (detail, timeline):
        assert response.status_code == 200
        _assert_next(response.json())

    assert detail.json()["customer"]["unionid"] == unionid
    assert timeline.json()["items"]


def test_user_ops_preview_routes_plan_without_real_external_calls(monkeypatch):
    client = _client(monkeypatch)
    first = client.get("/api/admin/user-ops/customers?limit=1").json()["items"][0]

    batch = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [first["id"]], "content": "hello"},
    )
    broadcast = client.post(
        "/api/admin/user-ops/broadcast/preview",
        json={"message": {"text": "hello"}, "selection_mode": "manual", "selected_ids": [first["id"]]},
    )
    export = client.post(
        "/api/admin/user-ops/export/preview",
        json={"filters": {}, "fields": ["customer_name", "mobile"]},
    )

    for response in (batch, broadcast, export):
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload.get("real_external_call_executed", False) is False
        safety = payload.get("side_effect_safety") or {}
        assert safety.get("side_effect_executed", False) is False
        assert payload.get("fallback_used", False) is False


def test_user_ops_batch_send_preview_supports_ai_audience_package_source(next_client, next_pg_schema) -> None:
    del next_pg_schema
    session_factory = get_session_factory()
    with session_factory() as session:
        package_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO ai_audience_package (
                        package_key, name, status, query_mode, identity_policy, created_at, updated_at
                    )
                    VALUES ('uo_ai_audience_pkg', 'User Ops AI Audience 包', 'active', 'hybrid', 'unionid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                    """
                )
            ).scalar_one()
        )
        session.execute(
            text(
                """
                INSERT INTO crm_user_identity (
                    unionid, primary_external_userid, external_userids_json, profile_json, status, created_at, updated_at
                )
                VALUES
                    ('union_ai_priority', 'wm_priority', '["wm_priority"]'::jsonb, '{"name":"优先客户"}'::jsonb, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    ('union_ai_skip', 'wm_skip', '["wm_skip"]'::jsonb, '{"name":"跳过客户"}'::jsonb, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (unionid) DO UPDATE SET
                    primary_external_userid = EXCLUDED.primary_external_userid,
                    external_userids_json = EXCLUDED.external_userids_json,
                    profile_json = EXCLUDED.profile_json,
                    updated_at = CURRENT_TIMESTAMP
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO ai_audience_member_current (
                    package_id, identity_type, identity_value, unionid, status, event_source_key, payload_hash
                )
                VALUES
                    (:package_id, 'unionid', 'union_ai_priority', 'union_ai_priority', 'active', 'event:1', 'hash:1'),
                    (:package_id, 'unionid', 'union_ai_skip', 'union_ai_skip', 'active', 'event:2', 'hash:2')
                """
            ),
            {"package_id": package_id},
        )
        session.execute(
            text(
                """
                INSERT INTO wecom_external_contact_follow_users (
                    external_userid, user_id, relation_status, remark
                )
                VALUES
                    ('wm_priority', 'HuangYouCan', 'active', '优先客户'),
                    ('wm_priority', 'QianLan', 'active', '优先客户'),
                    ('wm_skip', 'OtherUser', 'active', '跳过客户')
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO ai_audience_package_sender (
                    package_id, sender_userid, display_name, priority, status
                )
                VALUES
                    (:package_id, 'HuangYouCan', 'HuangYouCan', 2, 'active'),
                    (:package_id, 'QianLan', 'QianLan', 1, 'active')
                """
            ),
            {"package_id": package_id},
        )
        session.commit()

    response = next_client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={
            "selection_mode": "all_filtered",
            "target_source": "ai_audience_package",
            "target_source_id": package_id,
            "content": "hello",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["selected_count"] == 2
    assert payload["eligible_count"] == 1
    assert payload["skipped_by_reason"] == {"no_allowed_sender": 1}
    assert payload["owner_buckets"] == [
        {
            "owner_userid": "QianLan",
            "owner_display_name": "QianLan",
            "sender_userid": "QianLan",
            "target_count": 1,
            "target_unionids": ["union_ai_priority"],
            "external_userids": ["wm_priority"],
        }
    ]

    not_confirmed = next_client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={
            "selection_mode": "all_filtered",
            "target_source": "ai_audience_package",
            "target_source_id": package_id,
            "content": "hello",
            "confirm": False,
        },
    )
    assert not_confirmed.status_code == 400
    assert "confirm=true is required" in not_confirmed.text

    execute = next_client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={
            "selection_mode": "all_filtered",
            "target_source": "ai_audience_package",
            "target_source_id": package_id,
            "content": "hello",
            "confirm": True,
        },
    )
    assert execute.status_code == 200
    body = execute.json()
    assert body["sent_count"] == 1
    assert body["task_results"][0]["sender_userid"] == "QianLan"
    assert body["target_unionids"] == ["union_ai_priority"]
    assert body["side_effect_safety"]["side_effect_executed"] is False
