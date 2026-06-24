from __future__ import annotations

import json
from time import time

from sqlalchemy import text

from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
from aicrm_next.shared.db_session import get_session_factory


def _admin_cookies() -> dict[str, str]:
    return {
        SESSION_COOKIE: sign_session(
            {
                "auth_source": "break_glass",
                "login_type": "break_glass",
                "username": "admin",
                "display_name": "admin",
                "roles": ["super_admin"],
                "iat": int(time()),
            }
        )
    }


def _insert_package(
    session,
    *,
    package_key: str,
    name: str,
    status: str = "active",
    incremental_enabled: bool = True,
    daily_enabled: bool = False,
    incremental_interval_seconds: int = 180,
    daily_refresh_time: str = "03:00",
    updated_at: str = "2026-06-24 09:00:00+08",
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO ai_audience_package (
                    package_key, name, status, query_mode, identity_policy,
                    incremental_enabled, daily_enabled, incremental_interval_seconds,
                    daily_refresh_time, timezone, lookback_seconds, inbound_webhook_secret,
                    created_at, updated_at
                )
                VALUES (
                    :package_key, :name, :status, 'incremental_event', 'external_userid',
                    :incremental_enabled, :daily_enabled, :incremental_interval_seconds,
                    :daily_refresh_time, 'Asia/Shanghai', 600, 'secret-not-for-browser',
                    TIMESTAMPTZ '2026-06-24 08:50:00+08', CAST(:updated_at AS timestamptz)
                )
                RETURNING id
                """
            ),
            {
                "package_key": package_key,
                "name": name,
                "status": status,
                "incremental_enabled": incremental_enabled,
                "daily_enabled": daily_enabled,
                "incremental_interval_seconds": incremental_interval_seconds,
                "daily_refresh_time": daily_refresh_time,
                "updated_at": updated_at,
            },
        ).scalar_one()
    )


def _insert_member(session, *, package_id: int, identity_value: str, status: str = "active") -> None:
    session.execute(
        text(
            """
            INSERT INTO ai_audience_member_current (
                package_id, identity_type, identity_value, status, external_userid,
                event_source_key, payload_hash, payload_json
            )
            VALUES (
                :package_id, 'external_userid', :identity_value, :status, :identity_value,
                :event_source_key, :payload_hash, '{"hidden":"payload"}'::jsonb
            )
            """
        ),
        {
            "package_id": package_id,
            "identity_value": identity_value,
            "status": status,
            "event_source_key": f"event:{identity_value}",
            "payload_hash": f"hash:{identity_value}",
        },
    )


def _insert_run(session, *, package_id: int, refresh_finished_at: str, run_status: str = "succeeded") -> None:
    session.execute(
        text(
            """
            INSERT INTO ai_audience_package_run (
                package_id, run_type, status, refresh_started_at, refresh_finished_at,
                returned_count, entered_count, member_event_count
            )
            VALUES (
                :package_id, 'incremental', :run_status,
                CAST(:refresh_finished_at AS timestamptz) - interval '1 minute',
                CAST(:refresh_finished_at AS timestamptz),
                1, 1, 1
            )
            """
        ),
        {"package_id": package_id, "refresh_finished_at": refresh_finished_at, "run_status": run_status},
    )


def test_admin_ai_audience_packages_requires_admin_session(next_client) -> None:
    response = next_client.get("/api/admin/ai-audience/packages")

    assert response.status_code == 401
    assert response.json()["error"] == "admin_auth_required"


def test_admin_ai_audience_packages_api_returns_lightweight_read_model(next_client, next_pg_schema, monkeypatch) -> None:
    del next_pg_schema
    monkeypatch.setenv("SECRET_KEY", "ai-audience-admin-api-test")
    session_factory = get_session_factory()
    with session_factory() as session:
        no_run_id = _insert_package(
            session,
            package_key="admin_no_run",
            name="无运行记录人群包",
            incremental_interval_seconds=180,
            updated_at="2026-06-24 09:10:00+08",
        )
        counted_id = _insert_package(
            session,
            package_key="admin_counted",
            name="有成员与多次刷新人群包",
            incremental_interval_seconds=300,
            updated_at="2026-06-24 09:09:00+08",
        )
        daily_id = _insert_package(
            session,
            package_key="admin_daily",
            name="每日快照人群包",
            incremental_enabled=False,
            daily_enabled=True,
            daily_refresh_time="03:00",
            updated_at="2026-06-24 09:08:00+08",
        )
        hybrid_id = _insert_package(
            session,
            package_key="admin_hybrid",
            name="增量加每日人群包",
            incremental_enabled=True,
            daily_enabled=True,
            incremental_interval_seconds=180,
            daily_refresh_time="03:00",
            updated_at="2026-06-24 09:07:00+08",
        )
        _insert_package(
            session,
            package_key="admin_archived",
            name="归档不展示",
            status="archived",
            updated_at="2026-06-24 09:11:00+08",
        )
        _insert_member(session, package_id=counted_id, identity_value="wm_active_1")
        _insert_member(session, package_id=counted_id, identity_value="wm_active_2")
        _insert_member(session, package_id=counted_id, identity_value="wm_exited", status="exited")
        _insert_run(session, package_id=counted_id, refresh_finished_at="2026-06-24 09:01:00+08")
        _insert_run(session, package_id=counted_id, refresh_finished_at="2026-06-24 09:05:12+08")
        session.commit()

    response = next_client.get("/api/admin/ai-audience/packages", cookies=_admin_cookies())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    payload = response.json()
    assert payload["ok"] is True
    assert payload["total"] == 4
    assert [item["package_key"] for item in payload["items"]] == [
        "admin_no_run",
        "admin_counted",
        "admin_daily",
        "admin_hybrid",
    ]
    by_key = {item["package_key"]: item for item in payload["items"]}
    assert by_key["admin_no_run"] == {
        "id": no_run_id,
        "package_key": "admin_no_run",
        "name": "无运行记录人群包",
        "member_count": 0,
        "last_refreshed_at": None,
        "refresh_mode_label": "每 3 分钟",
    }
    assert by_key["admin_counted"] == {
        "id": counted_id,
        "package_key": "admin_counted",
        "name": "有成员与多次刷新人群包",
        "member_count": 2,
        "last_refreshed_at": "2026-06-24T09:05:12+08:00",
        "refresh_mode_label": "每 5 分钟",
    }
    assert by_key["admin_daily"]["id"] == daily_id
    assert by_key["admin_daily"]["refresh_mode_label"] == "每日 03:00"
    assert by_key["admin_hybrid"]["id"] == hybrid_id
    assert by_key["admin_hybrid"]["refresh_mode_label"] == "每 3 分钟 + 每日 03:00"

    response_text = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "sql_text",
        "incremental_sql_text",
        "snapshot_sql_text",
        "inbound_webhook_secret",
        "signing_secret",
        "payload_json",
        "headers_json",
        "wm_active_1",
        "wm_active_2",
        "wm_exited",
        "归档不展示",
    ):
        assert forbidden not in response_text
