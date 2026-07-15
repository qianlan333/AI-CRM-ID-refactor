from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.media_library.dto import GroupInviteUpsertRequest
from aicrm_next.media_library.repo import InMemoryMediaLibraryRepository


VALID_JOIN_URL = "https://work.weixin.qq.com/gm/0123456789abcdef0123456789abcdef"


def test_group_invite_request_accepts_wecom_gm_url_and_rejects_other_links() -> None:
    request = GroupInviteUpsertRequest(
        name="体验群邀请",
        title="点击加入体验群",
        description="进群领取资料",
        join_url=VALID_JOIN_URL,
        config_id="join-way-1",
        chat_id_list=["wr_group_1"],
    )

    assert request.join_url == VALID_JOIN_URL
    assert request.title == "点击加入体验群"

    with pytest.raises(ValueError, match="work.weixin.qq.com/gm"):
        GroupInviteUpsertRequest(title="错误链接", join_url="https://example.com/group")


def test_group_invite_in_memory_repository_crud() -> None:
    repo = InMemoryMediaLibraryRepository()
    created = repo.save_item(
        "group_invite",
        {
            "name": "体验群邀请",
            "title": "点击加入体验群",
            "description": "进群领取资料",
            "join_url": VALID_JOIN_URL,
            "pic_url": "https://example.com/group-cover.png",
            "config_id": "join-way-1",
            "state": "campaign-a",
            "chat_id_list": ["wr_group_1"],
            "auto_create_room": True,
            "room_base_name": "体验群",
            "room_base_id": 10,
            "enabled": True,
        },
    )

    assert created["join_url"] == VALID_JOIN_URL
    listed = repo.list_items("group_invite", limit=20, offset=0, filters={"enabled_only": True})
    assert any(item["id"] == created["id"] for item in listed["items"])

    updated = repo.save_item("group_invite", {"description": "更新后的描述", "enabled": False}, str(created["id"]))
    assert updated["description"] == "更新后的描述"
    assert updated["enabled"] is False

    deleted = repo.delete_item("group_invite", str(created["id"]))
    assert deleted["deleted"] is True


def test_group_invite_admin_api_and_page_contract() -> None:
    client = TestClient(create_app())

    page = client.get("/admin/group-invite-library")
    assert page.status_code == 200
    assert "客户群邀请设置" in page.text
    assert "已同步客户群" in page.text
    assert "/api/admin/automation-conversion/group-ops/groups" in page.text
    assert "work.weixin.qq.com/gm" in page.text
    assert "素材名称" not in page.text
    assert "卡片标题" not in page.text
    assert "企微入群方式 config_id" not in page.text
    assert "卡片封面 URL" not in page.text

    created = client.post(
        "/api/admin/group-invite-library",
        json={
            "name": "API 体验群",
            "title": "点击加入 API 体验群",
            "description": "无需扫码",
            "join_url": VALID_JOIN_URL,
            "chat_id_list": ["wr_group_1"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["ok"] is True
    assert payload["real_external_call_executed"] is False
    item_id = payload["item"]["id"]

    listed = client.get("/api/admin/group-invite-library?enabled_only=false").json()
    assert any(str(item["id"]) == str(item_id) for item in listed["items"])

    updated = client.put(
        f"/api/admin/group-invite-library/{item_id}",
        json={"description": "已更新", "enabled": False},
    ).json()
    assert updated["item"]["description"] == "已更新"

    deleted = client.delete(f"/api/admin/group-invite-library/{item_id}").json()
    assert deleted["deleted"] is True


def test_group_chat_picker_uses_synced_groups_and_only_enables_bound_groups() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "aicrm_next/frontend_compat/static/admin_console/material_picker.js"
    ).read_text(encoding="utf-8")

    assert "fetchGroupChatItems" in source
    assert "/api/admin/automation-conversion/group-ops/groups" in source
    assert "/api/admin/group-invite-library" in source
    assert 'group_invite: "客户群"' in source
    assert "selectable: Boolean(binding)" in source
    assert "请先配置邀请链接" in source
    assert "管理群邀请设置" in source
