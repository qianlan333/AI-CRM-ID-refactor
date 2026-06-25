from __future__ import annotations

import json
from typing import Any

from aicrm_next.customer_read_model.admin_business_profile import get_customer_business_profile
from aicrm_next.customer_read_model.application import GetCustomerContextQuery
from aicrm_next.customer_read_model.dto import CustomerContextRequest


PLACEHOLDERS = {
    "问卷信息": "questionnaire",
    "最近20条聊天信息": "recent_messages",
    "用户标签": "tags",
    "激活信息": "activation",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def referenced_context_keys(*parts: str) -> set[str]:
    blob = "\n".join(_text(part) for part in parts)
    return {key for placeholder, key in PLACEHOLDERS.items() if f"{{{{{placeholder}}}}}" in blob}


def _format_json_block(value: Any) -> str:
    if value in (None, "", [], {}):
        return "暂无"
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _questionnaire_block(profile: dict[str, Any]) -> str:
    answers = (
        dict(profile.get("business_profile") or {}).get("questionnaire_answers")
        or dict(profile.get("marketing_profile") or {}).get("matched_questions")
        or []
    )
    return _format_json_block(answers)


def _messages_block(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in messages[:20]:
        sender = _text(item.get("sender") or item.get("from"))
        content = _text(item.get("content") or item.get("summary"))
        send_time = _text(item.get("send_time") or item.get("event_time"))
        if content:
            lines.append(f"{send_time} {sender}: {content}".strip())
    return "\n".join(lines) if lines else "暂无"


def _activation_block(customer: dict[str, Any]) -> str:
    return _format_json_block(
        {
            "class_user_status": customer.get("class_user_status") or {},
            "marketing_summary": customer.get("marketing_summary") or {},
            "marketing_profile": customer.get("marketing_profile") or {},
        }
    )


def build_agent_context(external_userid: str, referenced_keys: set[str]) -> dict[str, Any]:
    context = GetCustomerContextQuery()(
        CustomerContextRequest(external_userid=external_userid, recent_message_limit=20, timeline_limit=20)
    )
    customer = dict(context.get("customer") or context.get("profile") or {})
    business_profile = {}
    if "questionnaire" in referenced_keys or "tags" in referenced_keys:
        profile_result = get_customer_business_profile(external_userid, limit=20)
        business_profile = dict(profile_result.get("business_profile") or {})
        customer = {**customer, "business_profile": business_profile}
    tags = list(business_profile.get("tags") or customer.get("tags") or [])
    recent_messages = list(context.get("recent_messages") or [])
    owner_userid = _text(
        customer.get("owner_userid")
        or dict(context.get("identity_binding_summary") or {}).get("owner_userid")
        or dict(customer.get("binding") or {}).get("owner_userid")
    )
    blocks: dict[str, str] = {}
    if "questionnaire" in referenced_keys:
        blocks["问卷信息"] = _questionnaire_block({**customer, "business_profile": business_profile})
    if "recent_messages" in referenced_keys:
        blocks["最近20条聊天信息"] = _messages_block(recent_messages)
    if "tags" in referenced_keys:
        blocks["用户标签"] = _format_json_block(tags)
    if "activation" in referenced_keys:
        blocks["激活信息"] = _activation_block(customer)
    return {
        "owner_userid": owner_userid,
        "customer": customer,
        "recent_messages": recent_messages[:20],
        "tags": tags,
        "blocks": blocks,
        "referenced_context_keys": sorted(referenced_keys),
        "raw_context": context,
    }


def render_chinese_placeholders(text: str, blocks: dict[str, str]) -> str:
    rendered = _text(text)
    for placeholder in PLACEHOLDERS:
        rendered = rendered.replace(f"{{{{{placeholder}}}}}", _text(blocks.get(placeholder)))
    return rendered

