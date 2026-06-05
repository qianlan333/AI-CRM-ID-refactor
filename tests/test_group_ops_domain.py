from __future__ import annotations

import pytest

from tests.group_ops_test_helpers import group_ops_repo


class FakeMediaLibraryRepo:
    def __init__(self) -> None:
        self.items = {
            ("image", "12"): {
                "id": 12,
                "enabled": True,
                "thumb_media_id": "image_media_12",
            },
            ("miniprogram", "34"): {
                "id": 34,
                "enabled": True,
                "appid": "wx_fixture",
                "pagepath": "pages/course/index",
                "title": "体验课",
                "thumb_media_id": "mini_thumb_34",
            },
            ("attachment", "56"): {
                "id": 56,
                "enabled": True,
                "media_id": "file_media_56",
            },
        }

    def get_item(self, kind: str, item_id: str, *, include_data: bool = True):
        return self.items.get((kind, str(item_id)))


def test_domain_validates_group_owner_match(group_ops_repo):
    from aicrm_next.automation_engine.group_ops.domain import assert_group_owned_by_plan
    from aicrm_next.shared.errors import ContractError

    plan = group_ops_repo.get_plan(1)
    owned_group = group_ops_repo.get_group_asset("wrOgAAA003")
    other_group = group_ops_repo.get_group_asset("wrOgBBB001")

    assert_group_owned_by_plan(group=owned_group, plan=plan)
    with pytest.raises(ContractError, match="owner_userid"):
        assert_group_owned_by_plan(group=other_group, plan=plan)


def test_domain_builds_text_only_private_message_payload():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(text="  课程入口  ", sender="owner_001")

    assert normalized == {"sender": "owner_001", "text": {"content": "课程入口"}}


def test_domain_builds_text_and_image_private_message_payload():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(text="课程入口", image_media_ids=["image_media_001"])

    assert normalized["text"]["content"] == "课程入口"
    assert normalized["attachments"] == [{"msgtype": "image", "image": {"media_id": "image_media_001"}}]


def test_domain_builds_text_and_file_attachment_payload():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(
        text="课程资料",
        attachments=[{"msgtype": "file", "file": {"media_id": "file_media_001"}}],
    )

    assert normalized["text"]["content"] == "课程资料"
    assert normalized["attachments"] == [{"msgtype": "file", "file": {"media_id": "file_media_001"}}]


def test_domain_builds_miniprogram_card_payload():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    normalized = normalize_message_content(
        text="课程入口",
        attachments=[
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
        sender="owner_001",
    )
    assert normalized["sender"] == "owner_001"
    assert normalized["attachments"][0]["miniprogram"]["pic_media_id"] == "MEDIA_ID"

    with pytest.raises(ContractError, match="pic_media_id"):
        normalize_message_content(
            text="",
            attachments=[
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {"appid": "wx123", "page": "/pages/course/today", "title": "课程入口"},
                }
            ],
        )

def test_domain_resolves_send_content_package_materials_into_message_payload():
    from aicrm_next.automation_engine.group_ops.content_builder import SendContentPackageResolver
    from aicrm_next.automation_engine.group_ops.domain import build_node_group_message_content

    normalized = build_node_group_message_content(
        node={
            "text_content": "",
            "attachments": [],
            "content_package_json": {
                "content_text": "素材包话术",
                "image_library_ids": [12],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            },
        },
        sender="owner_001",
        content_package_resolver=SendContentPackageResolver(FakeMediaLibraryRepo()),
    )

    assert normalized["sender"] == "owner_001"
    assert normalized["text"]["content"] == "素材包话术"
    assert normalized["attachments"] == [
        {
            "msgtype": "miniprogram",
            "miniprogram": {
                "appid": "wx_fixture",
                "page": "pages/course/index",
                "title": "体验课",
                "pic_media_id": "mini_thumb_34",
            },
        },
        {"msgtype": "file", "file": {"media_id": "file_media_56"}},
        {"msgtype": "image", "image": {"media_id": "image_media_12"}},
    ]


def test_domain_allows_empty_draft_but_rejects_empty_active_content():
    from aicrm_next.automation_engine.group_ops.content_builder import PrivateMessagePayloadBuilder
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    assert PrivateMessagePayloadBuilder().build({"sender": "owner_001"}, allow_empty_draft=True) == {"sender": "owner_001"}

    with pytest.raises(ContractError, match="content"):
        normalize_message_content(text="", attachments=[])


def test_domain_rejects_invalid_media_id():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    with pytest.raises(ContractError, match="media_id is invalid"):
        normalize_message_content(text="图片", image_media_ids=["bad media id"])


def test_group_ops_message_payload_can_be_consumed_by_next_action_dispatcher():
    from aicrm_next.automation_engine.group_ops.action_dispatcher import GroupOpsActionDispatcher
    from aicrm_next.automation_engine.group_ops.action_dispatcher import NextOutboundMessageQueueGateway
    from aicrm_next.automation_engine.group_ops.action_port import DefaultGroupOpsActionPort
    from aicrm_next.automation_engine.group_ops.domain import normalize_action_payload
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    captured: dict = {}

    def fake_insert_job(**kwargs):
        captured.update(kwargs)
        return 901

    message_payload = normalize_message_content(
        text="素材包话术",
        attachments=[{"msgtype": "file", "file": {"media_id": "file_media_001"}}],
    )
    action = normalize_action_payload({"action_type": "enqueue", "content_payload": message_payload})
    dispatcher = GroupOpsActionDispatcher(
        queue_gateway=NextOutboundMessageQueueGateway(insert_job=fake_insert_job),
    )

    result = DefaultGroupOpsActionPort(dispatcher).dispatch(
        {
            "plan_id": 1,
            "trigger_event_id": "evt_payload",
            "operator_member_id": "owner_001",
            "recipient": {"external_user_id": "wm_payload"},
            "action": action,
        }
    )

    assert result["status"] == "queued"
    assert captured["payload"]["text"]["content"] == "素材包话术"
    assert captured["payload"]["attachments"] == [{"msgtype": "file", "file": {"media_id": "file_media_001"}}]


def test_webhook_token_hash_verification_does_not_require_plaintext_storage():
    from aicrm_next.automation_engine.group_ops.domain import hash_webhook_token, verify_webhook_token

    token_hash = hash_webhook_token("secret-token")

    assert token_hash != "secret-token"
    assert verify_webhook_token(provided_token="secret-token", token_hash=token_hash) is True
    assert verify_webhook_token(provided_token="wrong", token_hash=token_hash) is False


def test_repository_guardrail_uses_sql_repository_in_production_mode(monkeypatch):
    from aicrm_next.automation_engine.group_ops.postgres_repo import PostgresGroupOpsRepository
    from aicrm_next.automation_engine.group_ops.repo import build_group_ops_repository

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://group_ops:group_ops@127.0.0.1:1/aicrm")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_GROUP_OPS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    repo = build_group_ops_repository()

    assert isinstance(repo, PostgresGroupOpsRepository)
    assert repo.source_status == "postgres_group_ops_repository"
