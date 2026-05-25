from __future__ import annotations

from tests.group_ops_test_helpers import error_code, group_ops_api_client


def test_plan_list_returns_plan_fields_without_next_action(group_ops_api_client):
    response = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/plans")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    plan_types = [item["plan_type"] for item in body["items"]]
    assert plan_types.count("standard") == 2
    assert plan_types.count("webhook") == 1
    required = {
        "plan_name",
        "plan_type",
        "owner_name",
        "bound_group_count",
        "today_estimated_reach",
        "status",
    }
    for item in body["items"]:
        assert required <= set(item)
        assert "next_action" not in item


def test_plan_group_binding_allows_only_owner_groups(group_ops_api_client):
    ok_response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/groups",
        json={"chat_id": "wrOgAAA003", "operator": "pytest"},
    )
    assert ok_response.status_code == 201
    assert ok_response.json()["summary"]["bound_group_count"] == 3

    bad_response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/groups",
        json={"chat_id": "wrOgBBB001", "operator": "pytest"},
    )
    assert bad_response.status_code in {400, 409}
    assert error_code(bad_response) == "group_owner_mismatch"


def test_standard_plan_nodes_save_and_list_in_domain_order(group_ops_api_client):
    created_plan = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans",
        json={
            "plan_name": "pytest 三日群运营",
            "plan_type": "standard",
            "owner_userid": "owner_001",
            "status": "draft",
            "operator": "pytest",
        },
    )
    assert created_plan.status_code == 201
    plan_id = created_plan.json()["item"]["id"]

    nodes = [
        (3, "第 3 天 20:00", "第三天复盘", 30),
        (1, "入群后 10 分钟", "欢迎语 + 课程入口", 10),
        (2, "第 2 天 12:30", "第二天提醒", 20),
    ]
    for day_index, trigger_time_label, action_title, sort_order in nodes:
        response = group_ops_api_client.post(
            f"/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes",
            json={
                "day_index": day_index,
                "trigger_time_label": trigger_time_label,
                "action_title": action_title,
                "text_content": f"{action_title}正文",
                "attachments": [
                    {
                        "msgtype": "miniprogram",
                        "miniprogram": {
                            "appid": "wx123",
                            "page": "/pages/course/today",
                            "title": "课程入口",
                            "pic_media_id": "MEDIA_ID",
                        },
                    }
                ],
                "sort_order": sort_order,
                "status": "active",
            },
        )
        assert response.status_code == 201

    listed = group_ops_api_client.get(f"/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["day_index"] for item in items] == [1, 2, 3]
    for item in items:
        assert {
            "day_index",
            "trigger_time_label",
            "action_title",
            "text_content",
            "attachments",
        } <= set(item)
        assert item["attachments"][0]["msgtype"] == "miniprogram"


def test_webhook_config_returns_no_plaintext_token_or_examples(group_ops_api_client):
    response = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/plans/2/webhook")

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "POST"
    assert body["webhook_url"].endswith("/api/automation/group-ops/webhooks/daily-lesson-8f3a")
    assert body["token_status"] == "generated"
    forbidden = {
        "token",
        "secret",
        "token_plaintext",
        "webhook_token",
        "request_example",
        "json_example",
        "usage",
        "description",
    }
    assert not (forbidden & set(body))
