from __future__ import annotations

from tests.group_ops_test_helpers import error_code, group_ops_api_client


def test_unsynced_groups_leave_new_plan_group_choices_empty(group_ops_api_client):
    from aicrm_next.automation_engine.group_ops.repo import reset_group_ops_fixture_state

    reset_group_ops_fixture_state(seed_groups=False)
    created = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans",
        json={"plan_name": "未同步群计划", "plan_type": "standard", "owner_userid": "owner_001", "status": "draft"},
    )
    plan_id = created.json()["item"]["id"]

    groups = group_ops_api_client.get(f"/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups")
    available = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_001")

    assert created.status_code == 201
    assert groups.status_code == 200
    assert groups.json()["items"] == []
    assert available.status_code == 200
    assert available.json()["items"] == []


def test_group_sync_writes_snapshots_and_filters_by_owner(group_ops_api_client, monkeypatch):
    from aicrm_next.automation_engine.group_ops.repo import reset_group_ops_fixture_state

    reset_group_ops_fixture_state(seed_groups=False)
    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")

    preview = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync/preview",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )
    after_preview = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_001")
    synced = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )
    owner_001 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_001")
    owner_002 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_002")

    assert preview.status_code == 200
    assert after_preview.status_code == 200
    assert after_preview.json()["items"] == []
    assert synced.status_code == 200
    assert synced.json()["synced_count"] == 3
    assert {item["owner_userid"] for item in owner_001.json()["items"]} == {"owner_001"}
    assert owner_002.json()["items"] == []


def test_group_sync_default_disabled_blocks_without_real_wecom(group_ops_api_client, monkeypatch):
    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    monkeypatch.delenv("AICRM_WECOM_GROUP_ADAPTER_MODE", raising=False)
    monkeypatch.setattr("wecom_ability_service.wecom_client.WeComClient.from_app", fail_if_called)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )

    assert response.status_code == 409
    assert error_code(response) == "wecom_group_sync_blocked"
