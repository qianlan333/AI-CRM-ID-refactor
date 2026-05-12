"""用户激活漏斗看板 — admin 路由 + 视图层测试."""
from __future__ import annotations

import pytest


@pytest.fixture()
def client(app):
    """覆盖顶层 client fixture: 注入 break_glass admin session 绕开 /login 重定向.

    与 tests/test_admin_console_phase4.py 同款做法 — 所有 /admin/* 路径都被
    register_admin_request_guards 守住, 没 admin session 会 302 到 /login,
    导致 page render 测试拿到 302 而不是 200.
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "hxc-dashboard-test-admin"
        sess["admin_session_break_glass_username"] = "hxc-dashboard-test-admin"
    return client


def _seed_snapshot(db, rows):
    for row in rows:
        db.execute(
            """
            INSERT INTO user_ops_hxc_dashboard_snapshot (
                mobile, phone_match_key,
                in_lead_pool, in_people, in_questionnaire,
                customer_name, external_userid, owner_userid,
                funnel_state, hxc_member_hit, hxc_user_hit,
                membership_type, membership_days_left,
                msg_user, hxc_nickname
            ) VALUES (
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?
            )
            """,
            (
                row["mobile"], row.get("phone_match_key", ""),
                row.get("in_lead_pool", False),
                row.get("in_people", False),
                row.get("in_questionnaire", False),
                row.get("customer_name", ""),
                row.get("external_userid", ""),
                row.get("owner_userid", ""),
                row["funnel_state"],
                row.get("hxc_member_hit", False),
                row.get("hxc_user_hit", False),
                row.get("membership_type", ""),
                row.get("membership_days_left"),
                row.get("msg_user", 0),
                row.get("hxc_nickname", ""),
            ),
        )
    db.commit()


def test_view_service_lists_rows_and_masks_mobile(app):
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.user_ops.hxc_dashboard_view_service import (
        list_hxc_dashboard_rows,
    )

    with app.app_context():
        _seed_snapshot(get_db(), [
            {
                "mobile": "13912345678",
                "funnel_state": "member_and_user",
                "in_lead_pool": True,
                "hxc_member_hit": True,
                "hxc_user_hit": True,
                "customer_name": "张三",
                "msg_user": 30,
            },
            {
                "mobile": "13800001111",
                "funnel_state": "only_member",
                "in_people": True,
                "hxc_member_hit": True,
                "membership_type": "trial",
                "membership_days_left": 5,
                "msg_user": 0,
            },
        ])

        rows = list_hxc_dashboard_rows()
        assert len(rows) == 2
        # msg_user 降序 → 30 在前
        assert rows[0]["mobile_masked"] == "139****5678"
        assert rows[0]["funnel_label"] == "已激活并打开"
        assert rows[0]["customer_name"] == "张三"
        assert rows[1]["mobile_masked"] == "138****1111"
        assert rows[1]["funnel_label"] == "仅激活未打开"
        assert rows[1]["membership_type"] == "trial"
        assert rows[1]["membership_days_left"] == 5


def test_summary_returns_funnel_buckets(app):
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.user_ops.hxc_dashboard_view_service import (
        get_dashboard_summary,
    )

    with app.app_context():
        _seed_snapshot(get_db(), [
            {"mobile": "13900000001", "funnel_state": "member_and_user",
             "hxc_member_hit": True, "hxc_user_hit": True, "membership_type": "member"},
            {"mobile": "13900000002", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial"},
            {"mobile": "13900000003", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial"},
            {"mobile": "13900000004", "funnel_state": "inactive"},
        ])
        summary = get_dashboard_summary()
        assert summary["total"] == 4
        assert summary["funnel"]["member_and_user"] == 1
        assert summary["funnel"]["only_member"] == 2
        assert summary["funnel"]["inactive"] == 1
        assert summary["member_hit"] == 3
        assert summary["user_hit"] == 1
        assert summary["member_count"] == 1
        assert summary["trial_count"] == 2


def test_admin_dashboard_page_renders(client, app):
    """GET /admin/hxc-dashboard 应该 200 + 含关键关键字 + 数据 JSON."""
    from wecom_ability_service.db import get_db

    with app.app_context():
        _seed_snapshot(get_db(), [
            {"mobile": "13912345678", "funnel_state": "member_and_user",
             "hxc_member_hit": True, "hxc_user_hit": True,
             "customer_name": "测试客户", "msg_user": 5},
        ])

    resp = client.get("/admin/hxc-dashboard")
    assert resp.status_code == 200, resp.data[:300]
    body = resp.data.decode("utf-8")
    # 页面壳
    assert "用户激活漏斗看板" in body
    assert "漏斗状态汇总" in body
    # nav 已注册
    assert "激活漏斗" in body
    # 数据 JSON 嵌入
    assert "139****5678" in body
    assert "测试客户" in body


def test_admin_refresh_endpoint_fails_when_not_configured(client, app):
    """没配 MESSAGE_ACTIVITY_DB_* → /refresh 返回 500 + status=not_configured."""
    with app.app_context():
        app.config.update(
            MESSAGE_ACTIVITY_DB_HOST="",
            MESSAGE_ACTIVITY_DB_NAME="",
            MESSAGE_ACTIVITY_DB_USER="",
            MESSAGE_ACTIVITY_DB_PASS="",
        )
    resp = client.post(
        "/api/admin/hxc-dashboard/refresh",
        json={"trigger_source": "admin"},
    )
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["status"] == "not_configured"
