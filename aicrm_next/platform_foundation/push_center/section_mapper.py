from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aicrm_next.platform_foundation.external_effects import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    AI_ASSIST_CAMPAIGN_MESSAGE_PLAN,
    FEISHU_WEBHOOK_NOTIFY,
    GROUP_OPS_MESSAGE_LOOPBACK,
    GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    MEDIA_STORAGE_UPLOAD,
    OPENCLAW_CONTEXT_PUSH,
    PAYMENT_ALIPAY_ORDER_QUERY,
    PAYMENT_ALIPAY_REFUND_QUERY,
    PAYMENT_WECHAT_ORDER_QUERY,
    PAYMENT_WECHAT_REFUND_QUERY,
    WEBHOOK_CUSTOMER_AUTOMATION_RETRY,
    WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE,
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    WECOM_MEDIA_UPLOAD,
    WECOM_MESSAGE_BROADCAST_SEND,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
    WECOM_WELCOME_MESSAGE_SEND,
)


@dataclass(frozen=True)
class PushSection:
    key: str
    label: str
    effect_types: tuple[str, ...]


SECTIONS: tuple[PushSection, ...] = (
    PushSection(
        "ai_assist",
        "AI 助手",
        (AI_ASSIST_CAMPAIGN_MESSAGE_PLAN, AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK, WECOM_MESSAGE_PRIVATE_SEND),
    ),
    PushSection("private_broadcast", "私信群发", (WECOM_MESSAGE_PRIVATE_SEND,)),
    PushSection(
        "group_ops",
        "群自动化运营",
        (GROUP_OPS_MESSAGE_LOOPBACK, GROUP_OPS_WEBHOOK_ACTION_LOOPBACK, WECOM_MESSAGE_GROUP_SEND),
    ),
    PushSection("group_broadcast", "群群发", (WECOM_MESSAGE_BROADCAST_SEND, WECOM_MESSAGE_GROUP_SEND)),
    PushSection("questionnaire", "问卷外推", (WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,)),
    PushSection("order", "订单外推", (WEBHOOK_ORDER_PAID_PUSH,)),
    PushSection("customer_webhook", "客户自动化 Webhook", (WEBHOOK_CUSTOMER_AUTOMATION_RETRY, WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE)),
    PushSection("tags", "企微标签", (WECOM_CONTACT_TAG_MARK, WECOM_CONTACT_TAG_UNMARK)),
    PushSection("welcome", "欢迎语", (WECOM_WELCOME_MESSAGE_SEND,)),
    PushSection("payment", "支付查询", (PAYMENT_WECHAT_ORDER_QUERY, PAYMENT_WECHAT_REFUND_QUERY, PAYMENT_ALIPAY_ORDER_QUERY, PAYMENT_ALIPAY_REFUND_QUERY)),
    PushSection("integrations", "集成推送", (FEISHU_WEBHOOK_NOTIFY, OPENCLAW_CONTEXT_PUSH, MEDIA_STORAGE_UPLOAD, WECOM_MEDIA_UPLOAD)),
    PushSection("other", "其他", ()),
)

SECTION_BY_KEY = {section.key: section for section in SECTIONS}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _job_value(job: Any, key: str) -> Any:
    if isinstance(job, dict):
        return job.get(key)
    return getattr(job, key, "")


def effect_types_for_section(section: str) -> list[str]:
    item = SECTION_BY_KEY.get(_text(section))
    return list(item.effect_types) if item else []


def label_for_section(section: str) -> str:
    item = SECTION_BY_KEY.get(_text(section))
    return item.label if item else SECTION_BY_KEY["other"].label


def section_for_job(job: Any) -> str:
    effect_type = _text(_job_value(job, "effect_type"))
    business_type = _text(_job_value(job, "business_type"))
    if effect_type in {AI_ASSIST_CAMPAIGN_MESSAGE_PLAN, AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK}:
        return "ai_assist"
    if effect_type == WECOM_MESSAGE_PRIVATE_SEND:
        if business_type == "ai_assist_campaign":
            return "ai_assist"
        if business_type in {"user_ops_broadcast", "private_broadcast"}:
            return "private_broadcast"
        return "private_broadcast"
    if effect_type in {GROUP_OPS_MESSAGE_LOOPBACK, GROUP_OPS_WEBHOOK_ACTION_LOOPBACK}:
        return "group_ops"
    if effect_type == WECOM_MESSAGE_GROUP_SEND:
        if business_type == "group_ops_plan":
            return "group_ops"
        if business_type == "group_broadcast":
            return "group_broadcast"
        return "group_ops"
    if effect_type == WECOM_MESSAGE_BROADCAST_SEND:
        return "group_broadcast"
    if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH:
        return "questionnaire"
    if effect_type == WEBHOOK_ORDER_PAID_PUSH:
        return "order"
    if effect_type in {WEBHOOK_CUSTOMER_AUTOMATION_RETRY, WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE}:
        return "customer_webhook"
    if effect_type in {WECOM_CONTACT_TAG_MARK, WECOM_CONTACT_TAG_UNMARK}:
        return "tags"
    if effect_type == WECOM_WELCOME_MESSAGE_SEND:
        return "welcome"
    if effect_type in {PAYMENT_WECHAT_ORDER_QUERY, PAYMENT_WECHAT_REFUND_QUERY, PAYMENT_ALIPAY_ORDER_QUERY, PAYMENT_ALIPAY_REFUND_QUERY}:
        return "payment"
    if effect_type in {FEISHU_WEBHOOK_NOTIFY, OPENCLAW_CONTEXT_PUSH, MEDIA_STORAGE_UPLOAD, WECOM_MEDIA_UPLOAD}:
        return "integrations"
    return "other"


def all_sections() -> list[dict[str, Any]]:
    return [{"key": item.key, "label": item.label, "effect_types": list(item.effect_types)} for item in SECTIONS]
