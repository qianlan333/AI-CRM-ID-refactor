from __future__ import annotations

import json
from typing import Any

from flask import current_app

from ...customer_center.routes import parse_customer_filters
from ...customer_center.service import get_customer_detail, list_customers
from ...customer_timeline import get_customer_timeline
from ...customer_timeline.routes import parse_timeline_filters
from ...services import (
    backfill_owner_class_terms_into_lead_pool,
    count_external_contact_identity_maps,
    get_group_chat_map,
    get_latest_questionnaire_submit_debug,
    get_owner_role,
    get_routing_config,
    get_signup_status_definition,
    get_user_ops_overview,
    import_activation_status_source,
    import_mobile_class_term_source,
    list_class_user_management_records,
    list_class_user_status_history,
    list_questionnaires,
    list_user_ops_history,
    list_user_ops_pool,
    migrate_class_user_status_from_contact_tags,
    resolve_contact_routing_context,
    run_due_user_ops_deferred_jobs,
    update_questionnaire,
    disable_questionnaire,
    get_questionnaire_detail,
    format_message_row,
    extract_roomid_from_raw_payload,
)
from ...infra.settings import get_setting
from ..admin_config.service import list_mcp_tool_settings, mcp_tool_enabled
from ..admin_config import repo as admin_config_repo
from ..questionnaire import build_questionnaire_preflight_payload
from ..tags.service import mark_customer_tags, unmark_customer_tags
from ..tasks.service import dispatch_wecom_task
from . import repo

TARGET_CUSTOMER_TAG_ACTION = "customer_tag_action"
TARGET_CUSTOMER_TASK_ACTION = "customer_task_action"
TARGET_QUESTIONNAIRE_ACTION = "questionnaire_console_action"
TARGET_OPERATIONS_ACTION = "operations_console_action"
TARGET_MCP_PREFLIGHT_ACTION = "mcp_preflight"
TARGET_MCP_SAMPLE_CALL_ACTION = "mcp_sample_call"

MCP_HIGH_RISK_TOOLS = {
    "mark_tags",
    "unmark_tags",
    "update_customer_tags",
    "create_private_message_task",
    "create_group_message_task",
    "create_moment_task",
    "record_conversion_feedback",
    "ack_message_batch",
}

MCP_NATIVE_DRY_RUN_TOOLS = {
    "create_private_message_task",
    "create_group_message_task",
    "create_moment_task",
}

MCP_TOOL_SERVICE_MAP: dict[str, dict[str, Any]] = {
    "resolve_customer": {
        "application_service": "Customer resolution aggregate",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._build_customer_context_payload",
            "wecom_ability_service.customer_center.service.get_customer_detail",
        ],
        "note": "客户定位；可附带 customer context / timeline / recent messages。",
    },
    "get_contact": {
        "application_service": "Contact snapshot read",
        "service_paths": ["wecom_ability_service.services.get_contact_by_external_userid"],
        "note": "读取单个客户 contact 快照。",
    },
    "get_customer_context": {
        "application_service": "Customer context aggregate",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._build_customer_context_payload",
            "wecom_ability_service.customer_timeline.service.get_customer_timeline",
        ],
        "note": "聚合 customer center、timeline、recent messages。",
    },
    "get_messages": {
        "application_service": "Archive message history read",
        "service_paths": ["wecom_ability_service.services.get_messages_by_user"],
        "note": "读取 archived_messages 全量历史。",
    },
    "get_recent_messages": {
        "application_service": "Archive recent message read",
        "service_paths": ["wecom_ability_service.services.get_recent_messages_by_user"],
        "note": "读取最近消息摘要。",
    },
    "search_messages": {
        "application_service": "Archive message search",
        "service_paths": ["wecom_ability_service.services.search_messages"],
        "note": "按 external_userid + keyword 搜索消息。",
    },
    "get_group_chat": {
        "application_service": "Group chat snapshot read",
        "service_paths": ["wecom_ability_service.services.get_group_chat_by_chat_id"],
        "note": "读取群聊快照。",
    },
    "mark_tags": {
        "application_service": "Customer tag mutate",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._update_customer_tags",
            "wecom_ability_service.wecom_client.WeComClient.mark_tag",
        ],
        "note": "写 WeCom 标签并更新本地 tag snapshot。",
    },
    "unmark_tags": {
        "application_service": "Customer tag mutate",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._update_customer_tags",
            "wecom_ability_service.wecom_client.WeComClient.mark_tag",
        ],
        "note": "写 WeCom 标签并移除本地 tag snapshot。",
    },
    "update_customer_tags": {
        "application_service": "Customer tag mutate",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._update_customer_tags",
            "wecom_ability_service.wecom_client.WeComClient.mark_tag",
        ],
        "note": "统一 add/remove tags 的组合写入口。",
    },
    "create_private_message_task": {
        "application_service": "Outbound private message task",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._call_business_task",
            "wecom_ability_service.mcp_adapter._call_wecom_task",
        ],
        "note": "支持 business input 和 raw payload；dry_run 默认开启。",
    },
    "create_group_message_task": {
        "application_service": "Outbound group message task",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._call_business_task",
            "wecom_ability_service.mcp_adapter._call_wecom_task",
        ],
        "note": "群发 welcome / followup 任务；dry_run 默认开启。",
    },
    "create_moment_task": {
        "application_service": "Outbound moment task",
        "service_paths": [
            "wecom_ability_service.mcp_adapter._call_business_task",
            "wecom_ability_service.mcp_adapter._call_wecom_task",
        ],
        "note": "企业微信朋友圈任务；dry_run 默认开启。",
    },
    "record_conversion_feedback": {
        "application_service": "Conversion feedback write",
        "service_paths": ["wecom_ability_service.services.record_conversion_feedback"],
        "note": "写 conversion feedback，不支持 runtime dry_run。",
    },
    "get_owner_role_map": {
        "application_service": "Owner role config read",
        "service_paths": ["wecom_ability_service.services.list_owner_role_map"],
        "note": "读取 owner_role_map 运行时配置。",
    },
    "get_signup_tag_rules": {
        "application_service": "Signup tag rules read",
        "service_paths": ["wecom_ability_service.services.get_signup_tag_rules_config"],
        "note": "读取 signup_tag_rules 运行时配置。",
    },
    "get_routing_config": {
        "application_service": "Routing runtime read",
        "service_paths": ["wecom_ability_service.services.get_routing_config"],
        "note": "读取 owner/routing runtime 聚合。",
    },
    "get_pending_message_batches": {
        "application_service": "Archive batch queue read",
        "service_paths": [
            "wecom_ability_service.services.materialize_message_batches",
            "wecom_ability_service.services.list_message_batches",
        ],
        "note": "读取待确认 message batches。",
    },
    "get_message_batch": {
        "application_service": "Archive batch detail read",
        "service_paths": [
            "wecom_ability_service.services.materialize_message_batches",
            "wecom_ability_service.services.get_message_batch",
        ],
        "note": "读取单个 message batch 详情。",
    },
    "ack_message_batch": {
        "application_service": "Archive batch ack write",
        "service_paths": ["wecom_ability_service.services.ack_message_batch"],
        "note": "确认 batch，存在状态写入。",
    },
    "get_owner_recent_chat_dump": {
        "application_service": "Owner recent chat dump aggregate",
        "service_paths": ["wecom_ability_service.mcp_adapter._build_owner_recent_chat_dump"],
        "note": "按顾问聚合 private / group 最近聊天。",
    },
    "get_hourly_followup_candidates": {
        "application_service": "Followup candidate scoring",
        "service_paths": ["wecom_ability_service.mcp_adapter._build_followup_candidates"],
        "note": "基于 archived_messages + tags + class status 生成跟进候选。",
    },
}

MCP_TOOL_SAMPLE_ARGS: dict[str, dict[str, Any]] = {
    "resolve_customer": {"customer_ref": "13800138000", "include_context": True},
    "get_contact": {"external_userid": "wm_test_external_001"},
    "get_customer_context": {"external_userid": "wm_test_external_001", "recent_message_limit": 10, "timeline_limit": 10},
    "get_messages": {"external_userid": "wm_test_external_001", "chat_type": "private"},
    "get_recent_messages": {"external_userid": "wm_test_external_001", "limit": 10},
    "search_messages": {"external_userid": "wm_test_external_001", "keyword": "报名"},
    "get_group_chat": {"chat_id": "chat-test-001"},
    "mark_tags": {"external_userid": "wm_test_external_001", "userid": "sales_01", "add_tag": ["tag_signup_001"]},
    "unmark_tags": {"external_userid": "wm_test_external_001", "userid": "sales_01", "remove_tag": ["tag_signup_001"]},
    "update_customer_tags": {"external_userid": "wm_test_external_001", "userid": "sales_01", "add_tags": ["tag_signup_001"]},
    "create_private_message_task": {"external_userid": "wm_test_external_001", "content": "你好，跟进一下你的报名进度"},
    "create_group_message_task": {"external_userid": "wm_test_external_001", "content": "群里同步一条报名说明"},
    "create_moment_task": {"external_userid": "wm_test_external_001", "content": "发布一期课程动态"},
    "record_conversion_feedback": {"external_userid": "wm_test_external_001", "feedback_type": "manual_note", "actor": "crm_console"},
    "get_owner_role_map": {"active_only": True},
    "get_signup_tag_rules": {},
    "get_routing_config": {},
    "get_pending_message_batches": {"limit": 20},
    "get_message_batch": {"batch_id": 1, "limit": 50},
    "ack_message_batch": {"batch_id": 1, "ack_note": "checked from console", "acked_by": "crm_console"},
    "get_owner_recent_chat_dump": {"owner_userid": "sales_01", "lookback_minutes": 60},
    "get_hourly_followup_candidates": {"limit": 10, "lookback_hours": 24},
}

MCP_TOOL_SAMPLE_OUTPUTS: dict[str, dict[str, Any]] = {
    "resolve_customer": {"ok": True, "external_userid": "wm_test_external_001", "matched_by": "mobile"},
    "get_contact": {"external_userid": "wm_test_external_001", "customer_name": "测试客户"},
    "get_customer_context": {"ok": True, "customer": {"external_userid": "wm_test_external_001"}, "timeline": {"count": 5}},
    "get_messages": {"messages": [{"msgtype": "text", "content": "你好"}]},
    "get_recent_messages": {"messages": [{"msgtype": "text", "content": "最近一条消息"}]},
    "search_messages": {"messages": [{"keyword": "报名", "content": "我想报名"}]},
    "get_group_chat": {"chat_id": "chat-test-001", "group_name": "测试群"},
    "mark_tags": {"ok": True, "result": {"ok": True}},
    "unmark_tags": {"ok": True, "result": {"ok": True}},
    "update_customer_tags": {"ok": True, "results": {"mark": {"ok": True}}},
    "create_private_message_task": {"ok": True, "dry_run": True, "would_execute": True},
    "create_group_message_task": {"ok": True, "dry_run": True, "would_execute": True},
    "create_moment_task": {"ok": True, "dry_run": True, "would_execute": True},
    "record_conversion_feedback": {"ok": True, "feedback_id": 1},
    "get_owner_role_map": {"items": [{"userid": "sales_01", "role": "sales"}]},
    "get_signup_tag_rules": {"tag_group_name": "AI 产品报名情况"},
    "get_routing_config": {"routing_rules": {"signed_999": {"routing_target": "manual_review"}}},
    "get_pending_message_batches": {"items": [{"id": 1, "status": "pending"}]},
    "get_message_batch": {"id": 1, "items": []},
    "ack_message_batch": {"id": 1, "status": "acked"},
    "get_owner_recent_chat_dump": {"owner_userid": "sales_01", "private_conversations": []},
    "get_hourly_followup_candidates": {"ok": True, "candidates": [{"external_userid": "wm_test_external_001", "score": 8}]},
}

OPERATIONS_TABS = (
    {"key": "overview", "label": "总览"},
    {"key": "user-ops", "label": "User Ops 列表"},
    {"key": "history", "label": "User Ops 历史"},
    {"key": "imports", "label": "导入"},
    {"key": "deferred", "label": "Deferred Jobs"},
    {"key": "class-users", "label": "Class User"},
    {"key": "class-history", "label": "Class History"},
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _operator(value: Any) -> str:
    return _normalized_text(value) or "crm_console"


def _split_csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_normalized_text(item) for item in value if _normalized_text(item)]
    normalized = _normalized_text(value)
    if not normalized:
        return []
    parts = normalized.replace("\n", ",").replace("，", ",").split(",")
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        item = _normalized_text(part)
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _audit_log(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    admin_config_repo.insert_admin_operation_log(
        operator=_operator(operator),
        action_type=_normalized_text(action_type),
        target_type=_normalized_text(target_type),
        target_id=_normalized_text(target_id),
        before_json=before or {},
        after_json=after or {},
    )


def build_customer_list_payload(args: Any) -> dict[str, Any]:
    filters = parse_customer_filters(args)
    payload = list_customers(filters)
    rows = payload.get("items") or payload.get("customers") or []
    owner_options = sorted(
        {
            (str(item.get("owner_userid") or "").strip(), str(item.get("owner_display_name") or "").strip())
            for item in rows
            if str(item.get("owner_userid") or "").strip()
        },
        key=lambda item: item[1] or item[0],
    )
    return {
        **payload,
        "customers": rows,
        "owner_options": [{"userid": userid, "display_name": display_name or userid} for userid, display_name in owner_options],
        "filters": payload.get("filters") or filters,
    }


def _build_recent_messages(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = repo.list_recent_customer_messages(external_userid, limit=limit)
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        message = format_message_row(row, group_map=group_map)
        items.append(
            {
                "id": int(row["id"]),
                "send_time": _normalized_text(row.get("send_time")) or _normalized_text(row.get("created_at")),
                "chat_type": _normalized_text(row.get("chat_type")),
                "msgtype": _normalized_text(message.get("msgtype") or row.get("msgtype")),
                "sender": _normalized_text(message.get("from") or row.get("sender")),
                "receiver": _normalized_text(row.get("receiver")),
                "content": _normalized_text(message.get("content") or row.get("content")),
                "room_name": _normalized_text(message.get("room_name")),
                "raw_payload": message,
            }
        )
    return items


def _build_customer_questionnaire_rows(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = repo.list_customer_questionnaire_history(external_userid, limit=limit)
    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                **row,
                "final_tags": _json_loads(row.get("final_tags"), default=[]),
            }
        )
    return results


def build_customer_detail_payload(external_userid: str) -> dict[str, Any] | None:
    detail = get_customer_detail(external_userid)
    if not detail:
        return None
    owner_role = get_owner_role(_normalized_text(detail.get("owner_userid"))) or {}
    signup_status = _normalized_text((detail.get("class_user_status") or {}).get("signup_status"))
    routing_context = resolve_contact_routing_context(
        _normalized_text(detail.get("owner_userid")),
        _normalized_text(owner_role.get("role")),
        signup_status,
    )
    timeline = get_customer_timeline(external_userid, parse_timeline_filters({"limit": "20", "offset": "0", "event_type": ""}))
    recent_messages = _build_recent_messages(external_userid, limit=20)
    questionnaire_rows = _build_customer_questionnaire_rows(external_userid, limit=20)
    outbound_tasks = repo.list_customer_outbound_tasks(external_userid, limit=20)
    routing_definition = get_signup_status_definition(signup_status) or {}
    return {
        "customer": detail,
        "owner_role": owner_role,
        "routing_context": routing_context,
        "routing_definition": routing_definition,
        "timeline": timeline or {"items": [], "total": 0, "count": 0},
        "recent_messages": recent_messages,
        "questionnaire_history": questionnaire_rows,
        "outbound_tasks": outbound_tasks,
        "tag_count": len(detail.get("tags") or []),
    }


def preview_customer_tag_action(
    *,
    external_userid: str,
    userid: str,
    action: str,
    tag_ids: list[str],
) -> dict[str, Any]:
    detail = get_customer_detail(external_userid)
    if not detail:
        raise ValueError("customer not found")
    normalized_action = _normalized_text(action)
    if normalized_action not in {"mark", "unmark"}:
        raise ValueError("action must be mark or unmark")
    normalized_userid = _normalized_text(userid) or _normalized_text(detail.get("owner_userid"))
    if not normalized_userid:
        raise ValueError("userid is required")
    normalized_tag_ids = _split_csv(tag_ids)
    if not normalized_tag_ids:
        raise ValueError("tag_ids is required")
    current_tags = [dict(item) for item in (detail.get("tags") or [])]
    return {
        "ok": True,
        "dry_run": True,
        "would_execute": True,
        "action": normalized_action,
        "external_userid": _normalized_text(external_userid),
        "userid": normalized_userid,
        "tag_ids": normalized_tag_ids,
        "current_tags": current_tags,
        "preview_payload": {
            "userid": normalized_userid,
            "external_userid": _normalized_text(external_userid),
            "add_tag": normalized_tag_ids if normalized_action == "mark" else [],
            "remove_tag": normalized_tag_ids if normalized_action == "unmark" else [],
        },
    }


def execute_customer_tag_action(
    *,
    external_userid: str,
    userid: str,
    action: str,
    tag_ids: list[str],
    operator: str,
) -> dict[str, Any]:
    preview = preview_customer_tag_action(
        external_userid=external_userid,
        userid=userid,
        action=action,
        tag_ids=tag_ids,
    )
    payload = dict(preview["preview_payload"])
    if preview["action"] == "mark":
        result = mark_customer_tags(payload)
    else:
        result = unmark_customer_tags(payload)
    after_detail = get_customer_detail(external_userid) or {}
    _audit_log(
        operator=operator,
        action_type=f"execute_{preview['action']}",
        target_type=TARGET_CUSTOMER_TAG_ACTION,
        target_id=_normalized_text(external_userid),
        before={"tags": preview["current_tags"], "userid": preview["userid"]},
        after={
            "tags": after_detail.get("tags") or [],
            "payload": payload,
            "result": result,
        },
    )
    return {
        **preview,
        "dry_run": False,
        "executed": True,
        "result": result,
        "current_tags": after_detail.get("tags") or [],
    }


def preview_customer_task_action(
    *,
    external_userid: str,
    task_type: str,
    userid: str,
    content: str,
) -> dict[str, Any]:
    detail = get_customer_detail(external_userid)
    if not detail:
        raise ValueError("customer not found")
    normalized_task_type = _normalized_text(task_type)
    if normalized_task_type not in {"private_message", "group_message", "moment"}:
        raise ValueError("task_type must be private_message, group_message or moment")
    normalized_userid = _normalized_text(userid) or _normalized_text(detail.get("owner_userid"))
    normalized_content = _normalized_text(content)
    if not normalized_content:
        raise ValueError("content is required")
    if not normalized_userid:
        raise ValueError("userid is required")
    if normalized_task_type == "private_message":
        payload = {
            "chat_type": "single",
            "external_userid": [_normalized_text(external_userid)],
            "sender": [normalized_userid],
            "text": {"content": normalized_content},
        }
    elif normalized_task_type == "group_message":
        payload = {
            "chat_type": "group",
            "external_userid": [_normalized_text(external_userid)],
            "sender": [normalized_userid],
            "text": {"content": normalized_content},
        }
    else:
        payload = {
            "visible_range": {"sender_list": {"userid": [normalized_userid]}},
            "text": {"content": normalized_content},
        }
    return {
        "ok": True,
        "dry_run": True,
        "would_execute": True,
        "external_userid": _normalized_text(external_userid),
        "task_type": normalized_task_type,
        "userid": normalized_userid,
        "content": normalized_content,
        "preview_payload": payload,
    }


def execute_customer_task_action(
    *,
    external_userid: str,
    task_type: str,
    userid: str,
    content: str,
    operator: str,
) -> dict[str, Any]:
    preview = preview_customer_task_action(
        external_userid=external_userid,
        task_type=task_type,
        userid=userid,
        content=content,
    )
    mapping = {
        "private_message": "create_private_message_task",
        "group_message": "create_group_message_task",
        "moment": "create_moment_task",
    }
    result = dispatch_wecom_task(preview["task_type"], mapping[preview["task_type"]], dict(preview["preview_payload"]))
    _audit_log(
        operator=operator,
        action_type=f"execute_{preview['task_type']}",
        target_type=TARGET_CUSTOMER_TASK_ACTION,
        target_id=_normalized_text(external_userid),
        before={"preview_payload": preview["preview_payload"]},
        after=result,
    )
    return {
        **preview,
        "dry_run": False,
        "executed": True,
        "result": result,
    }


def _questionnaire_paths(slug: str) -> dict[str, str]:
    normalized_slug = _normalized_text(slug)
    return {
        "public_path": f"/s/{normalized_slug}" if normalized_slug else "",
        "submitted_path": f"/s/{normalized_slug}/submitted" if normalized_slug else "",
    }


def build_questionnaire_index_payload() -> dict[str, Any]:
    questionnaires = []
    for item in list_questionnaires():
        questionnaires.append({**item, **_questionnaire_paths(_normalized_text(item.get("slug")))})
    preflight_error = ""
    try:
        def _lightweight_tag_probe() -> list[dict[str, Any]]:
            required_keys = ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET", "WECOM_API_BASE"]
            missing = [key for key in required_keys if not _normalized_text(current_app.config.get(key))]
            if missing:
                raise RuntimeError(f"missing config: {', '.join(missing)}")
            return [{"tag_id": "config-ok", "tag_name": "config-ok"}]

        preflight = build_questionnaire_preflight_payload(
            config=current_app.config,
            list_available_wecom_tags_fn=_lightweight_tag_probe,
            count_external_contact_identity_maps_fn=count_external_contact_identity_maps,
        )
    except Exception as exc:
        preflight = {
            "ok": False,
            "wechat_oauth_configured": False,
            "wecom_contact_configured": False,
            "debug_session_api_enabled": False,
            "questionnaire_admin_ui_enabled": True,
            "wecom_tags_api_available": False,
            "identity_map_available": False,
        }
        preflight_error = str(exc)
    return {
        "questionnaires": questionnaires,
        "preflight": preflight,
        "preflight_error": preflight_error,
    }


def build_questionnaire_detail_payload(questionnaire_id: int) -> dict[str, Any] | None:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        return None
    detail = {
        **questionnaire,
        **_questionnaire_paths(_normalized_text(questionnaire.get("slug"))),
    }
    return {
        "questionnaire": detail,
        "latest_submit_debug": get_latest_questionnaire_submit_debug(int(questionnaire_id)),
        "submissions": [
            {
                **row,
                "final_tags": _json_loads(row.get("final_tags"), default=[]),
            }
            for row in repo.list_questionnaire_submissions(int(questionnaire_id), limit=50)
        ],
        "apply_logs": [
            {
                **row,
                "final_tags": _json_loads(row.get("final_tags"), default=[]),
            }
            for row in repo.list_questionnaire_apply_logs(int(questionnaire_id), limit=50)
        ],
    }


def parse_questionnaire_editor_form(form: Any) -> dict[str, Any]:
    questions_json = _normalized_text(form.get("questions_json"))
    score_rules_json = _normalized_text(form.get("score_rules_json"))
    questions = _json_loads(questions_json, default=[])
    score_rules = _json_loads(score_rules_json, default=[])
    if questions_json and not isinstance(questions, list):
        raise ValueError("questions_json must be a JSON array")
    if score_rules_json and not isinstance(score_rules, list):
        raise ValueError("score_rules_json must be a JSON array")
    return {
        "name": _normalized_text(form.get("name")),
        "slug": _normalized_text(form.get("slug")),
        "title": _normalized_text(form.get("title")),
        "description": _normalized_text(form.get("description")),
        "redirect_url": _normalized_text(form.get("redirect_url")),
        "is_disabled": _normalize_bool(form.get("is_disabled")),
        "questions": questions,
        "score_rules": score_rules,
    }


def save_questionnaire_editor(
    questionnaire_id: int,
    *,
    form: Any,
    operator: str,
) -> dict[str, Any]:
    before = get_questionnaire_detail(int(questionnaire_id))
    if not before:
        raise ValueError("questionnaire not found")
    payload = parse_questionnaire_editor_form(form)
    updated = update_questionnaire(int(questionnaire_id), payload)
    if not updated:
        raise ValueError("questionnaire not found")
    _audit_log(
        operator=operator,
        action_type="save_questionnaire",
        target_type=TARGET_QUESTIONNAIRE_ACTION,
        target_id=str(int(questionnaire_id)),
        before=before,
        after=updated,
    )
    return updated


def toggle_questionnaire_disabled(questionnaire_id: int, *, is_disabled: bool, operator: str) -> dict[str, Any]:
    before = get_questionnaire_detail(int(questionnaire_id))
    if not before:
        raise ValueError("questionnaire not found")
    updated = disable_questionnaire(int(questionnaire_id), is_disabled)
    if not updated:
        raise ValueError("questionnaire not found")
    _audit_log(
        operator=operator,
        action_type="disable_questionnaire" if is_disabled else "enable_questionnaire",
        target_type=TARGET_QUESTIONNAIRE_ACTION,
        target_id=str(int(questionnaire_id)),
        before=before,
        after=updated,
    )
    return updated


def operations_tabs(active_key: str) -> list[dict[str, Any]]:
    normalized = _normalized_text(active_key) or "overview"
    return [
        {
            **item,
            "active": item["key"] == normalized,
            "href": f"/admin/user-ops?tab={item['key']}",
        }
        for item in OPERATIONS_TABS
    ]


def build_operations_payload(args: Any) -> dict[str, Any]:
    active_tab = _normalized_text(args.get("tab")) or "overview"
    if active_tab not in {item["key"] for item in OPERATIONS_TABS}:
        active_tab = "overview"
    overview = get_user_ops_overview()
    user_ops_filters = {
        "is_wecom_added": _normalized_text(args.get("is_wecom_added")),
        "is_mobile_bound": _normalized_text(args.get("is_mobile_bound")),
        "huangxiaocan_activation_state": _normalized_text(args.get("huangxiaocan_activation_state")),
        "class_term_no": _normalized_text(args.get("class_term_no")),
        "owner_userid": _normalized_text(args.get("owner_userid")),
        "query": _normalized_text(args.get("query")),
    }
    class_status_filter = _normalized_text(args.get("signup_status"))
    history_limit = _normalized_int(args.get("limit"), default=100, minimum=1, maximum=200)
    user_ops_list_payload = list_user_ops_pool(**user_ops_filters) if active_tab in {"overview", "user-ops"} else {}
    user_ops_history_payload = list_user_ops_history(limit=history_limit) if active_tab in {"overview", "history"} else {}
    class_user_payload = (
        list_class_user_management_records(signup_status=class_status_filter) if active_tab in {"overview", "class-users"} else {}
    )
    class_history_payload = list_class_user_status_history(limit=history_limit) if active_tab in {"overview", "class-history"} else {}
    deferred_jobs = repo.list_deferred_jobs(limit=50) if active_tab in {"overview", "deferred"} else []
    import_batches = repo.list_recent_user_ops_import_batches(limit=20) if active_tab in {"overview", "imports"} else []
    recent_audit = repo.list_recent_admin_operation_logs(target_type=TARGET_OPERATIONS_ACTION, limit=20)
    return {
        "active_tab": active_tab,
        "tabs": operations_tabs(active_tab),
        "overview": overview,
        "user_ops_filters": user_ops_filters,
        "class_status_filter": class_status_filter,
        "user_ops_list": user_ops_list_payload,
        "user_ops_history": user_ops_history_payload,
        "class_user_list": class_user_payload,
        "class_user_history": class_history_payload,
        "deferred_jobs": deferred_jobs,
        "import_batches": import_batches,
        "recent_audit": recent_audit,
        "mcp_auth_configured": bool(_normalized_text(get_setting("MCP_BEARER_TOKEN"))),
        "mcp_get_routing_enabled": mcp_tool_enabled("get_routing_config"),
    }


def execute_operations_action(
    *,
    action: str,
    form: Any,
    files: Any,
    operator: str,
) -> dict[str, Any]:
    normalized_action = _normalized_text(action)
    operator_value = _operator(operator)
    if normalized_action == "backfill-owner-class-terms":
        owner_userid = _normalized_text(form.get("owner_userid"))
        class_term_min = _normalized_int(form.get("class_term_min"), default=1, minimum=1, maximum=99)
        class_term_max = _normalized_int(form.get("class_term_max"), default=5, minimum=1, maximum=99)
        confirm = _normalize_bool(form.get("confirm"))
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid=owner_userid,
            class_term_min=class_term_min,
            class_term_max=class_term_max,
            dry_run=not confirm,
            operator=operator_value,
            entry_source=_normalized_text(form.get("entry_source")),
        )
        _audit_log(
            operator=operator_value,
            action_type="apply_backfill_owner_class_terms" if confirm else "preview_backfill_owner_class_terms",
            target_type=TARGET_OPERATIONS_ACTION,
            target_id=owner_userid,
            before={"action": normalized_action, "confirm": confirm},
            after=payload,
        )
        return payload

    if normalized_action == "run-deferred-jobs":
        if not _normalize_bool(form.get("confirm")):
            raise ValueError("confirm is required before running deferred jobs")
        limit = _normalized_int(form.get("limit"), default=20, minimum=1, maximum=200)
        payload = run_due_user_ops_deferred_jobs(limit=limit)
        _audit_log(
            operator=operator_value,
            action_type="run_deferred_jobs",
            target_type=TARGET_OPERATIONS_ACTION,
            target_id=f"limit:{limit}",
            before={"action": normalized_action},
            after=payload,
        )
        return payload

    if normalized_action == "migrate-class-user":
        if not _normalize_bool(form.get("confirm")):
            raise ValueError("confirm is required before running class-user migrate")
        payload = migrate_class_user_status_from_contact_tags()
        _audit_log(
            operator=operator_value,
            action_type="migrate_class_user_status",
            target_type=TARGET_OPERATIONS_ACTION,
            target_id="class_user_status",
            before={"action": normalized_action},
            after=payload,
        )
        return payload

    if normalized_action in {"import-mobile-class-terms", "import-activation-status"}:
        if not _normalize_bool(form.get("confirm")):
            raise ValueError("confirm is required before import")
        uploaded_file = files.get("file") if files else None
        pasted_text = _normalized_text(form.get("pasted_text"))
        if not uploaded_file and not pasted_text:
            raise ValueError("file or pasted_text is required")
        if normalized_action == "import-mobile-class-terms":
            if uploaded_file and uploaded_file.filename:
                payload = import_mobile_class_term_source(
                    file_name=uploaded_file.filename,
                    file_bytes=uploaded_file.read(),
                    created_by=operator_value,
                )
            else:
                payload = import_mobile_class_term_source(
                    pasted_text=pasted_text,
                    created_by=operator_value,
                )
        else:
            if uploaded_file and uploaded_file.filename:
                payload = import_activation_status_source(
                    file_name=uploaded_file.filename,
                    file_bytes=uploaded_file.read(),
                    created_by=operator_value,
                )
            else:
                payload = import_activation_status_source(
                    pasted_text=pasted_text,
                    created_by=operator_value,
                )
        _audit_log(
            operator=operator_value,
            action_type=normalized_action.replace("-", "_"),
            target_type=TARGET_OPERATIONS_ACTION,
            target_id=str(payload.get("batch_id") or normalized_action),
            before={"action": normalized_action},
            after=payload,
        )
        return payload

    raise ValueError("unsupported operations action")


def _mcp_default_tool_defs() -> list[dict[str, Any]]:
    from ...mcp_adapter import TOOL_DEFS

    return [dict(item) for item in TOOL_DEFS]


def _mcp_defaults_map() -> dict[str, dict[str, Any]]:
    return {
        _normalized_text(item.get("name")): dict(item)
        for item in _mcp_default_tool_defs()
        if _normalized_text(item.get("name"))
    }


def _mcp_auth_snapshot() -> dict[str, Any]:
    stored = _normalized_text(get_setting("MCP_BEARER_TOKEN"))
    config_value = _normalized_text(current_app.config.get("MCP_BEARER_TOKEN"))
    if stored:
        return {"configured": True, "source": "app_settings"}
    if config_value:
        return {"configured": True, "source": "config"}
    return {"configured": False, "source": "missing"}


def _mcp_risk_level(tool_name: str) -> str:
    return "high" if tool_name in MCP_HIGH_RISK_TOOLS else "read"


def _mcp_risk_label(tool_name: str) -> str:
    return "High Risk" if tool_name in MCP_HIGH_RISK_TOOLS else "Read Only"


def _build_schema_example(schema: dict[str, Any]) -> Any:
    schema = dict(schema or {})
    schema_type = _normalized_text(schema.get("type"))
    if schema_type == "object":
        properties = schema.get("properties") or {}
        if not isinstance(properties, dict):
            return {}
        result: dict[str, Any] = {}
        for key, value in properties.items():
            result[str(key)] = _build_schema_example(value if isinstance(value, dict) else {})
        return result
    if schema_type == "array":
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {"type": "string"}
        return [_build_schema_example(item_schema)]
    if schema_type == "integer":
        return int(schema.get("minimum") or 1)
    if schema_type == "number":
        return 1
    if schema_type == "boolean":
        return True
    enum_values = schema.get("enum") or []
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    return "string"


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _mcp_registry_rows(*, query: str, enabled_only: bool, visible_only: bool) -> list[dict[str, Any]]:
    payload = list_mcp_tool_settings(query=query, enabled_only=enabled_only)
    defaults = _mcp_defaults_map()
    rows: list[dict[str, Any]] = []
    for row in payload["rows"]:
        if visible_only and not row["visible_in_console"]:
            continue
        tool_name = _normalized_text(row.get("tool_name"))
        default = defaults.get(tool_name, {})
        mapping = MCP_TOOL_SERVICE_MAP.get(tool_name, {})
        sample_args = MCP_TOOL_SAMPLE_ARGS.get(tool_name) or _build_schema_example(default.get("inputSchema") or {})
        sample_output = MCP_TOOL_SAMPLE_OUTPUTS.get(tool_name) or {"ok": True}
        rows.append(
            {
                **row,
                "tool_name": tool_name,
                "category": _normalized_text(row.get("tool_group")) or "misc",
                "risk_level": _mcp_risk_level(tool_name),
                "risk_label": _mcp_risk_label(tool_name),
                "description": _normalized_text(row.get("description")) or _normalized_text(default.get("description")),
                "input_schema": default.get("inputSchema") or {},
                "input_schema_pretty": _pretty_json(default.get("inputSchema") or {}),
                "sample_args": sample_args,
                "sample_args_pretty": _pretty_json(sample_args),
                "sample_output": sample_output,
                "sample_output_pretty": _pretty_json(sample_output),
                "application_service": _normalized_text(mapping.get("application_service")) or "Runtime helper",
                "service_paths": mapping.get("service_paths") or ["wecom_ability_service.mcp_adapter._call_tool"],
                "service_note": _normalized_text(mapping.get("note")),
            }
        )
    return rows


def build_mcp_console_payload(args: Any) -> dict[str, Any]:
    from ...mcp_adapter import get_mcp_http_info

    query = _normalized_text(args.get("q"))
    enabled_only = _normalize_bool(args.get("enabled_only"))
    visible_only = _normalize_bool(args.get("visible_only"))
    rows = _mcp_registry_rows(query=query, enabled_only=enabled_only, visible_only=visible_only)
    auth = _mcp_auth_snapshot()
    dependency_snapshot = repo.get_mcp_dependency_snapshot()
    last_preflight_logs = repo.list_recent_admin_operation_logs(target_type=TARGET_MCP_PREFLIGHT_ACTION, limit=5)
    last_sample_logs = repo.list_recent_admin_operation_logs(target_type=TARGET_MCP_SAMPLE_CALL_ACTION, limit=10)
    latest_preflight = last_preflight_logs[0] if last_preflight_logs else {}

    routing_detail = "routing config ready"
    routing_ok = True
    try:
        routing_payload = get_routing_config()
        routing_rules = routing_payload.get("routing_rules") if isinstance(routing_payload, dict) else {}
        routing_detail = f"{len(routing_rules or {})} routing rules"
    except Exception as exc:
        routing_ok = False
        routing_detail = str(exc)

    task_required_keys = ["WECOM_CORP_ID", "WECOM_SECRET", "WECOM_AGENT_ID", "WECOM_API_BASE"]
    task_missing_keys = [key for key in task_required_keys if not _normalized_text(current_app.config.get(key))]
    dependency_checks = [
        {
            "label": "Database",
            "status": "ok" if dependency_snapshot["database_ok"] else "danger",
            "value": dependency_snapshot["database_backend"],
            "detail": "CRM backend database connection",
        },
        {
            "label": "Contacts Read Model",
            "status": "ok" if int(dependency_snapshot.get("contacts_total") or 0) >= 0 else "danger",
            "value": dependency_snapshot.get("contacts_total") or 0,
            "detail": _normalized_text(dependency_snapshot.get("contacts_latest_updated_at")) or "no contacts snapshot yet",
        },
        {
            "label": "Archive Message Store",
            "status": "ok" if int(dependency_snapshot.get("archived_messages_total") or 0) >= 0 else "danger",
            "value": dependency_snapshot.get("archived_messages_total") or 0,
            "detail": _normalized_text(dependency_snapshot.get("archived_messages_latest_send_time")) or "no archived messages yet",
        },
        {
            "label": "Routing Runtime",
            "status": "ok" if routing_ok else "danger",
            "value": "ready" if routing_ok else "error",
            "detail": routing_detail,
        },
        {
            "label": "Task Dispatch Config",
            "status": "ok" if not task_missing_keys else "warn",
            "value": "ready" if not task_missing_keys else "missing",
            "detail": ", ".join(task_missing_keys) if task_missing_keys else "WeCom task config present",
        },
        {
            "label": "Pending Message Batches",
            "status": "warn" if int(dependency_snapshot.get("message_batches_pending") or 0) else "ok",
            "value": dependency_snapshot.get("message_batches_pending") or 0,
            "detail": f"total batches {int(dependency_snapshot.get('message_batches_total') or 0)}",
        },
    ]

    summary_cards = [
        {"label": "Registry Tools", "value": len(rows), "description": "后台可检索到的 MCP tools"},
        {"label": "Enabled", "value": sum(1 for item in rows if item["enabled"]), "description": "运行时允许调用"},
        {"label": "Visible", "value": sum(1 for item in rows if item["visible_in_console"]), "description": "registry 中可见"},
        {"label": "High Risk", "value": sum(1 for item in rows if item["risk_level"] == "high"), "description": "默认仅 dry-run / 二次确认"},
    ]

    return {
        "filters": {"q": query, "enabled_only": enabled_only, "visible_only": visible_only},
        "registry_rows": rows,
        "summary_cards": summary_cards,
        "runtime": {
            **get_mcp_http_info(),
            "auth_configured": auth["configured"],
            "auth_source": auth["source"],
            "enabled_tool_count": sum(1 for item in rows if item["enabled"]),
            "latest_preflight": latest_preflight.get("after_json") or {},
        },
        "dependency_checks": dependency_checks,
        "latest_preflight_log": latest_preflight,
        "recent_preflight_logs": last_preflight_logs,
        "recent_sample_logs": last_sample_logs,
    }


def _mcp_request_headers() -> dict[str, str]:
    auth_value = _normalized_text(get_setting("MCP_BEARER_TOKEN")) or _normalized_text(current_app.config.get("MCP_BEARER_TOKEN"))
    headers = {"Accept": "application/json"}
    if auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"
    return headers


def run_mcp_preflight(*, operator: str) -> dict[str, Any]:
    request_id = 1
    initialize_payload = {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {}}
    list_payload = {"jsonrpc": "2.0", "id": request_id + 1, "method": "tools/list", "params": {}}
    headers = _mcp_request_headers()
    with current_app.test_client() as client:
        health_response = client.get("/mcp", headers=headers)
        initialize_response = client.post("/mcp", headers=headers, json=initialize_payload)
        tools_list_response = client.post("/mcp", headers=headers, json=list_payload)

    health_json = health_response.get_json(silent=True) or {}
    initialize_json = initialize_response.get_json(silent=True) or {}
    tools_list_json = tools_list_response.get_json(silent=True) or {}
    tools = (((tools_list_json.get("result") or {}).get("tools")) if isinstance(tools_list_json, dict) else []) or []
    auth = _mcp_auth_snapshot()

    result = {
        "ok": health_response.status_code == 200 and initialize_response.status_code == 200 and tools_list_response.status_code == 200,
        "endpoint_status": health_response.status_code,
        "initialize_status": initialize_response.status_code,
        "tools_list_status": tools_list_response.status_code,
        "endpoint_payload": health_json,
        "initialize_payload": initialize_json,
        "tools_list_count": len(tools),
        "tool_names": [_normalized_text(item.get("name")) for item in tools if isinstance(item, dict)],
        "auth_configured": auth["configured"],
        "auth_source": auth["source"],
    }
    _audit_log(
        operator=operator,
        action_type="run_mcp_preflight",
        target_type=TARGET_MCP_PREFLIGHT_ACTION,
        target_id="/mcp",
        before={"headers": {"has_auth_header": "Authorization" in headers}},
        after=result,
    )
    return result


def _normalize_mcp_runtime_result(result: dict[str, Any]) -> dict[str, Any]:
    text_preview = ""
    content = result.get("content") or []
    if isinstance(content, list):
        first_text = next(
            (
                _normalized_text(item.get("text"))
                for item in content
                if isinstance(item, dict) and _normalized_text(item.get("text"))
            ),
            "",
        )
        text_preview = first_text
    return {
        "raw_result": result,
        "structured_content": result.get("structuredContent"),
        "content_text": text_preview,
        "result_pretty": _pretty_json(result.get("structuredContent") if "structuredContent" in result else result),
    }


def run_mcp_sample_call(
    *,
    tool_name: str,
    arguments_json: str,
    live_run: bool,
    confirm_high_risk: bool,
    operator: str,
) -> dict[str, Any]:
    from ...mcp_adapter import execute_mcp_tool_runtime

    normalized_tool_name = _normalized_text(tool_name)
    registry_rows = _mcp_registry_rows(query="", enabled_only=False, visible_only=False)
    registry_map = {item["tool_name"]: item for item in registry_rows}
    if normalized_tool_name not in registry_map:
        raise ValueError("unknown tool_name")

    arguments = _json_loads(arguments_json, default=None)
    if not isinstance(arguments, dict):
        raise ValueError("arguments_json must be a JSON object")

    tool_row = registry_map[normalized_tool_name]
    high_risk = normalized_tool_name in MCP_HIGH_RISK_TOOLS
    requested_live = bool(live_run)
    if requested_live and high_risk and not confirm_high_risk:
        raise ValueError("confirm_high_risk is required for high-risk tools")

    warnings: list[str] = []
    mode = "live" if requested_live else "preview"
    payload = dict(arguments)

    if not tool_row["enabled"]:
        result = {
            "ok": False,
            "mode": mode,
            "tool_name": normalized_tool_name,
            "error": "tool is disabled in runtime",
            "preview_payload": payload,
        }
    elif not requested_live and normalized_tool_name in MCP_NATIVE_DRY_RUN_TOOLS:
        payload["dry_run"] = True
        payload["confirm"] = False
        result = {
            "ok": True,
            "mode": mode,
            "tool_name": normalized_tool_name,
            "dry_run": True,
            "runtime_result": _normalize_mcp_runtime_result(execute_mcp_tool_runtime(normalized_tool_name, payload)),
        }
    elif not requested_live and high_risk:
        warnings.append("tool has no native dry_run support; console only shows request preview")
        result = {
            "ok": True,
            "mode": mode,
            "tool_name": normalized_tool_name,
            "dry_run": True,
            "preview_only": True,
            "preview_payload": payload,
            "warnings": warnings,
        }
    else:
        if requested_live and normalized_tool_name in MCP_NATIVE_DRY_RUN_TOOLS:
            payload["dry_run"] = False
            payload["confirm"] = True
        runtime_result = execute_mcp_tool_runtime(normalized_tool_name, payload)
        result = {
            "ok": True,
            "mode": mode,
            "tool_name": normalized_tool_name,
            "dry_run": False if requested_live else None,
            "runtime_result": _normalize_mcp_runtime_result(runtime_result),
            "warnings": warnings,
        }

    _audit_log(
        operator=operator,
        action_type="execute_mcp_sample_call" if requested_live else "preview_mcp_sample_call",
        target_type=TARGET_MCP_SAMPLE_CALL_ACTION,
        target_id=normalized_tool_name,
        before={
            "tool_name": normalized_tool_name,
            "live_run": requested_live,
            "confirm_high_risk": bool(confirm_high_risk),
            "arguments": arguments,
        },
        after=result,
    )
    return {
        **result,
        "tool_name": normalized_tool_name,
        "risk_level": _mcp_risk_level(normalized_tool_name),
        "requested_live": requested_live,
        "submitted_arguments": arguments,
        "submitted_arguments_pretty": _pretty_json(arguments),
        "preview_payload_pretty": _pretty_json(result.get("preview_payload") or {}) if result.get("preview_payload") is not None else "",
    }
