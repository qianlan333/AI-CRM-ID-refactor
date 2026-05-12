"""用户激活漏斗看板 — 外部 API (Bearer token) 路由测试."""
from __future__ import annotations


_TOKEN = "test-hxc-api-token"


def _seed(db, rows):
    for row in rows:
        db.execute(
            """
            INSERT INTO user_ops_hxc_dashboard_snapshot (
                mobile, funnel_state,
                in_lead_pool, in_people, in_questionnaire,
                customer_name, owner_userid, class_term_label,
                hxc_member_hit, hxc_user_hit,
                membership_type, msg_user
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["mobile"], row["funnel_state"],
                row.get("in_lead_pool", False),
                row.get("in_people", False),
                row.get("in_questionnaire", False),
                row.get("customer_name", ""),
                row.get("owner_userid", ""),
                row.get("class_term_label", ""),
                row.get("hxc_member_hit", False),
                row.get("hxc_user_hit", False),
                row.get("membership_type", ""),
                row.get("msg_user", 0),
            ),
        )
    db.commit()


def test_api_list_rejects_missing_token(client, app):
    with app.app_context():
        app.config["HXC_DASHBOARD_API_TOKEN"] = _TOKEN
    resp = client.get("/api/v1/hxc-dashboard/list")
    assert resp.status_code == 401


def test_api_list_rejects_wrong_token(client, app):
    with app.app_context():
        app.config["HXC_DASHBOARD_API_TOKEN"] = _TOKEN
    resp = client.get(
        "/api/v1/hxc-dashboard/list",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_api_list_503_when_not_configured(client, app):
    with app.app_context():
        # 显式清空所有可能的 token 来源
        app.config["HXC_DASHBOARD_API_TOKEN"] = ""
        app.config["MCP_BEARER_TOKEN"] = ""
        app.config["AUTOMATION_INTERNAL_API_TOKEN"] = ""
    resp = client.get(
        "/api/v1/hxc-dashboard/list",
        headers={"Authorization": "Bearer anything"},
    )
    assert resp.status_code == 503


def test_api_list_returns_paginated_payload(client, app):
    from wecom_ability_service.db import get_db

    with app.app_context():
        app.config["HXC_DASHBOARD_API_TOKEN"] = _TOKEN
        _seed(get_db(), [
            {"mobile": "13900000001", "funnel_state": "member_and_user",
             "hxc_member_hit": True, "hxc_user_hit": True,
             "membership_type": "member", "owner_userid": "owner_a",
             "msg_user": 30},
            {"mobile": "13900000002", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial",
             "owner_userid": "owner_b", "msg_user": 0},
            {"mobile": "13900000003", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial",
             "owner_userid": "owner_a", "msg_user": 0},
        ])

    resp = client.get(
        "/api/v1/hxc-dashboard/list",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert resp.status_code == 200, resp.data[:200]
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["total"] == 3
    assert len(payload["items"]) == 3
    # 顶部 summary 也带回
    assert payload["summary"]["total"] == 3
    assert payload["summary"]["funnel"]["only_member"] == 2

    # 手机号必脱敏 — 外部 API 不返回原始 phone
    for row in payload["items"]:
        assert "****" in row["mobile_masked"]


def test_api_list_filter_by_funnel_state(client, app):
    from wecom_ability_service.db import get_db

    with app.app_context():
        app.config["HXC_DASHBOARD_API_TOKEN"] = _TOKEN
        _seed(get_db(), [
            {"mobile": "13900000001", "funnel_state": "member_and_user",
             "hxc_member_hit": True, "hxc_user_hit": True},
            {"mobile": "13900000002", "funnel_state": "only_member",
             "hxc_member_hit": True},
            {"mobile": "13900000003", "funnel_state": "only_member",
             "hxc_member_hit": True},
            {"mobile": "13900000004", "funnel_state": "inactive"},
        ])

    resp = client.get(
        "/api/v1/hxc-dashboard/list?funnel_state=only_member",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    payload = resp.get_json()
    assert payload["total"] == 2
    assert all(r["funnel_state"] == "only_member" for r in payload["items"])
    assert payload["filters"]["funnel_state"] == "only_member"


def test_api_list_filter_by_owner_and_limit(client, app):
    from wecom_ability_service.db import get_db

    with app.app_context():
        app.config["HXC_DASHBOARD_API_TOKEN"] = _TOKEN
        _seed(get_db(), [
            {"mobile": "13900000001", "funnel_state": "member_and_user",
             "owner_userid": "owner_a", "msg_user": 50},
            {"mobile": "13900000002", "funnel_state": "only_member",
             "owner_userid": "owner_a", "msg_user": 0},
            {"mobile": "13900000003", "funnel_state": "only_member",
             "owner_userid": "owner_b", "msg_user": 0},
        ])

    resp = client.get(
        "/api/v1/hxc-dashboard/list?owner_userid=owner_a&limit=1",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    payload = resp.get_json()
    assert payload["total"] == 2     # owner_a 总共 2 行
    assert len(payload["items"]) == 1  # 但 limit=1 只返回 1 条
    assert payload["items"][0]["owner_userid"] == "owner_a"


def test_api_summary_returns_only_summary(client, app):
    from wecom_ability_service.db import get_db

    with app.app_context():
        app.config["HXC_DASHBOARD_API_TOKEN"] = _TOKEN
        _seed(get_db(), [
            {"mobile": "13900000001", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial"},
        ])

    resp = client.get(
        "/api/v1/hxc-dashboard/summary",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["ok"] is True
    assert "summary" in payload
    assert "items" not in payload  # /summary 不返回明细
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["funnel"]["only_member"] == 1


def test_api_accepts_mcp_bearer_token_as_fallback(client, app):
    """复用 MCP_BEARER_TOKEN 做兜底鉴权, 给 MCP 集成方免重新分发凭据."""
    with app.app_context():
        # 关掉自己的 token, 只配 MCP 的
        app.config["HXC_DASHBOARD_API_TOKEN"] = ""
        app.config["MCP_BEARER_TOKEN"] = "fallback-mcp-token"

    resp = client.get(
        "/api/v1/hxc-dashboard/summary",
        headers={"Authorization": "Bearer fallback-mcp-token"},
    )
    assert resp.status_code == 200
