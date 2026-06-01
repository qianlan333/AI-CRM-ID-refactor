from __future__ import annotations

from tests.group_ops_test_helpers import group_ops_api_client


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


def test_group_sync_preview_does_not_write_snapshots(group_ops_api_client, monkeypatch):
    from aicrm_next.automation_engine.group_ops.repo import reset_group_ops_fixture_state

    reset_group_ops_fixture_state(seed_groups=False)
    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")

    preview = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync/preview",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )
    after_preview = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_001")

    assert preview.status_code == 200
    body = preview.json()
    assert len(body["items"]) >= 2
    assert body["total"] >= 2
    assert body["side_effect_safety"]["no_db_write"] is True
    assert body["side_effect_safety"]["no_outbound_send"] is True
    assert after_preview.status_code == 200
    assert after_preview.json()["items"] == []


def test_group_sync_writes_snapshots_and_reports_create_update(group_ops_api_client, monkeypatch):
    from aicrm_next.automation_engine.group_ops.repo import reset_group_ops_fixture_state

    reset_group_ops_fixture_state(seed_groups=False)
    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")

    synced = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )
    synced_again = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )
    owner_001 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_001")
    admin_001 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=admin_001")

    assert synced.status_code == 200
    assert synced.json()["synced_count"] >= 2
    assert synced.json()["new_count"] >= 2
    assert synced_again.status_code == 200
    assert synced_again.json()["updated_count"] >= 2
    assert {item["owner_userid"] for item in owner_001.json()["items"]} == {"owner_001"}
    assert admin_001.status_code == 200
    assert admin_001.json()["items"] == []


def test_group_sync_owner_filter_keeps_owners_separate(group_ops_api_client, monkeypatch):
    from aicrm_next.automation_engine.group_ops.repo import reset_group_ops_fixture_state

    reset_group_ops_fixture_state(seed_groups=False)
    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")

    group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_001", "limit": 10, "operator": "pytest"},
    )
    group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_002", "limit": 10, "operator": "pytest"},
    )
    owner_001 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_001")
    owner_002 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_002")
    admin_001 = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=admin_001")

    assert {item["owner_userid"] for item in owner_001.json()["items"]} == {"owner_001"}
    assert {item["owner_userid"] for item in owner_002.json()["items"]} == {"owner_002"}
    assert len(owner_001.json()["items"]) >= 2
    assert len(owner_002.json()["items"]) >= 1
    assert [item["chat_id"] for item in admin_001.json()["items"]] == ["wrOgBBB001"]
    assert admin_001.json()["items"][0]["admin_userids"] == ["admin_001"]


def test_group_sync_binding_owner_mismatch_is_rejected(group_ops_api_client, monkeypatch):
    from aicrm_next.automation_engine.group_ops.repo import reset_group_ops_fixture_state

    reset_group_ops_fixture_state(seed_groups=False)
    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")

    created = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans",
        json={"plan_name": "owner 001 计划", "plan_type": "standard", "owner_userid": "owner_001", "status": "draft"},
    )
    group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/groups/sync",
        json={"owner_userid": "owner_002", "limit": 10, "operator": "pytest"},
    )
    groups = group_ops_api_client.get("/api/admin/automation-conversion/group-ops/groups?owner_userid=owner_002")
    bad = group_ops_api_client.post(
        f"/api/admin/automation-conversion/group-ops/plans/{created.json()['item']['id']}/groups",
        json={"chat_id": groups.json()["items"][0]["chat_id"]},
    )

    assert bad.status_code == 400
    assert bad.json()["detail"]["error_code"] == "group_owner_mismatch"


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
    body = response.json()
    assert body["ok"] is False
    assert body["status"] in {"blocked", "disabled"}
    assert body["synced_count"] == 0


def test_group_sync_fake_adapter_data_is_stable(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupAssetAdapter

    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    monkeypatch.setattr("wecom_ability_service.wecom_client.WeComClient.from_app", fail_if_called)

    owner_001 = WeComGroupAssetAdapter(mode="fake").list_group_chats(owner_userid="owner_001", limit=100)
    owner_002 = WeComGroupAssetAdapter(mode="fake").list_group_chats(owner_userid="owner_002", limit=100)

    assert owner_001["ok"] is True
    assert owner_002["ok"] is True
    assert len(owner_001["groups"]) >= 2
    assert len(owner_002["groups"]) >= 1
