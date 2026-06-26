from __future__ import annotations

from typing import Any


SCHEMA_CATALOG: list[dict[str, Any]] = [
    {
        "name": "audience_read.identity_universe_v1",
        "description": "统一身份标准视图，汇总 person、企业微信 external_userid、手机号哈希和 owner_userid。",
        "columns": [
            {"name": "person_id", "type": "bigint"},
            {"name": "external_userid", "type": "text"},
            {"name": "mobile_hash", "type": "text"},
            {"name": "owner_userid", "type": "text"},
            {"name": "identity_type", "type": "text"},
            {"name": "identity_value", "type": "text"},
            {"name": "source_table", "type": "text"},
            {"name": "updated_at", "type": "timestamptz"},
        ],
        "required_filters": [],
        "recommended_filters": ["identity_type", "updated_at"],
        "example_sql": "SELECT identity_type, identity_value, identity_value AS event_source_key, jsonb_build_object('source_table', source_table) AS payload_json FROM audience_read.identity_universe_v1 WHERE updated_at >= :last_watermark_at",
    },
    {
        "name": "audience_read.questionnaire_submissions_v1",
        "description": "问卷提交标准事实视图。",
        "columns": [
            {"name": "submission_id", "type": "bigint"},
            {"name": "questionnaire_id", "type": "bigint"},
            {"name": "respondent_key", "type": "text"},
            {"name": "external_userid", "type": "text"},
            {"name": "mobile_hash", "type": "text"},
            {"name": "owner_userid", "type": "text"},
            {"name": "submitted_at", "type": "timestamptz"},
            {"name": "payload_json", "type": "jsonb"},
        ],
        "required_filters": [],
        "recommended_filters": ["questionnaire_id", "submitted_at"],
        "example_sql": "SELECT 'external_userid' AS identity_type, external_userid AS identity_value, 'questionnaire_submission:' || submission_id AS event_source_key, payload_json FROM audience_read.questionnaire_submissions_v1 WHERE questionnaire_id = :questionnaire_id AND submitted_at >= :last_watermark_at",
    },
    {
        "name": "audience_read.orders_v1",
        "description": "订单和支付标准事实视图。",
        "columns": [
            {"name": "order_id", "type": "bigint"},
            {"name": "out_trade_no", "type": "text"},
            {"name": "external_userid", "type": "text"},
            {"name": "mobile_hash", "type": "text"},
            {"name": "owner_userid", "type": "text"},
            {"name": "product_code", "type": "text"},
            {"name": "status", "type": "text"},
            {"name": "paid_at", "type": "timestamptz"},
            {"name": "payload_json", "type": "jsonb"},
        ],
        "required_filters": [],
        "recommended_filters": ["product_code", "paid_at", "status"],
        "example_sql": "SELECT 'external_userid' AS identity_type, external_userid AS identity_value, 'order:' || order_id AS event_source_key, payload_json FROM audience_read.orders_v1 WHERE paid_at >= :last_watermark_at AND status = 'paid'",
    },
    {
        "name": "audience_read.wecom_contacts_v1",
        "description": "企业微信联系人标准事实视图。",
        "columns": [
            {"name": "external_userid", "type": "text"},
            {"name": "unionid", "type": "text"},
            {"name": "openid", "type": "text"},
            {"name": "owner_userid", "type": "text"},
            {"name": "customer_name", "type": "text"},
            {"name": "status", "type": "text"},
            {"name": "updated_at", "type": "timestamptz"},
            {"name": "payload_json", "type": "jsonb"},
        ],
        "required_filters": [],
        "recommended_filters": ["owner_userid", "status", "updated_at"],
        "example_sql": "SELECT 'external_userid' AS identity_type, external_userid AS identity_value, 'wecom_contact:' || external_userid AS event_source_key, payload_json FROM audience_read.wecom_contacts_v1 WHERE status = 'active'",
    },
    {
        "name": "audience_read.channel_entries_v1",
        "description": "渠道进入事实视图，来自现有 channel contact / callback facts。",
        "columns": [
            {"name": "channel_entry_id", "type": "bigint"},
            {"name": "channel_id", "type": "bigint"},
            {"name": "channel_code", "type": "text"},
            {"name": "channel_name", "type": "text"},
            {"name": "scene_value", "type": "text"},
            {"name": "external_userid", "type": "text"},
            {"name": "owner_userid", "type": "text"},
            {"name": "last_entered_at", "type": "timestamptz"},
            {"name": "payload_json", "type": "jsonb"},
        ],
        "required_filters": [],
        "recommended_filters": ["channel_id", "scene_value", "last_entered_at"],
        "example_sql": "SELECT 'external_userid' AS identity_type, external_userid AS identity_value, 'channel_entry:' || channel_entry_id AS event_source_key, payload_json FROM audience_read.channel_entries_v1 WHERE last_entered_at >= :last_watermark_at",
    },
    {
        "name": "audience_read.group_chat_members_v1",
        "description": "企微客户群外部联系人成员视图，来自已缓存的 group_chats 详情 payload。",
        "columns": [
            {"name": "chat_id", "type": "text"},
            {"name": "group_name", "type": "text"},
            {"name": "owner_userid", "type": "text"},
            {"name": "external_userid", "type": "text"},
            {"name": "unionid", "type": "text"},
            {"name": "customer_name", "type": "text"},
            {"name": "group_nickname", "type": "text"},
            {"name": "invitor_userid", "type": "text"},
            {"name": "member_type", "type": "integer"},
            {"name": "join_scene", "type": "integer"},
            {"name": "joined_at", "type": "timestamptz"},
            {"name": "updated_at", "type": "timestamptz"},
            {"name": "payload_json", "type": "jsonb"},
        ],
        "required_filters": [],
        "recommended_filters": ["chat_id", "joined_at", "updated_at"],
        "example_sql": "SELECT 'external_userid' AS identity_type, external_userid AS identity_value, 'group_chat_member:' || chat_id || ':' || external_userid AS event_source_key, payload_json, external_userid, owner_userid, joined_at AS event_at FROM audience_read.group_chat_members_v1 WHERE chat_id = :chat_id",
    },
]


ALLOWED_VIEWS = frozenset(item["name"] for item in SCHEMA_CATALOG)


def schema_catalog_payload() -> dict[str, Any]:
    return {"views": SCHEMA_CATALOG}
