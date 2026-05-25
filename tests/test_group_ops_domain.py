from __future__ import annotations

import pytest

from tests.group_ops_test_helpers import group_ops_repo


def test_domain_validates_group_owner_match(group_ops_repo):
    from aicrm_next.automation_engine.group_ops.domain import assert_group_owned_by_plan
    from aicrm_next.shared.errors import ContractError

    plan = group_ops_repo.get_plan(1)
    owned_group = group_ops_repo.get_group_asset("wrOgAAA003")
    other_group = group_ops_repo.get_group_asset("wrOgBBB001")

    assert_group_owned_by_plan(group=owned_group, plan=plan)
    with pytest.raises(ContractError, match="owner_userid"):
        assert_group_owned_by_plan(group=other_group, plan=plan)


def test_domain_reuses_unified_attachment_validation():
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
    with pytest.raises(ContractError, match="content"):
        normalize_message_content(text="", attachments=[])


def test_webhook_token_hash_verification_does_not_require_plaintext_storage():
    from aicrm_next.automation_engine.group_ops.domain import hash_webhook_token, verify_webhook_token

    token_hash = hash_webhook_token("secret-token")

    assert token_hash != "secret-token"
    assert verify_webhook_token(provided_token="secret-token", token_hash=token_hash) is True
    assert verify_webhook_token(provided_token="wrong", token_hash=token_hash) is False


def test_application_fixture_guardrail_blocks_implicit_production_repo(monkeypatch):
    from aicrm_next.automation_engine.group_ops.application import CreateGroupOpsPlanCommand
    from aicrm_next.automation_engine.group_ops.dto import GroupOpsPlanCreateRequest

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://group_ops:group_ops@127.0.0.1:1/aicrm")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    result = CreateGroupOpsPlanCommand()(
        GroupOpsPlanCreateRequest(
            plan_name="生产应被阻断",
            plan_type="standard",
            owner_userid="owner_001",
            operator="pytest",
        )
    )

    assert result["ok"] is False
    assert result["status_code"] == 503
    assert result["source_status"] == "production_unavailable"
    assert result["side_effect_safety"]["real_wecom_call_executed"] is False
