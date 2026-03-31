from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from flask import Blueprint, Response, jsonify, request

from .customer_center import get_customer_detail
from .customer_timeline.service import get_customer_timeline
from .db import get_db
from .services import (
    ack_message_batch,
    extract_roomid_from_raw_payload,
    format_message_row,
    get_contact_by_external_userid,
    get_group_chat_map,
    get_message_batch,
    get_messages_by_user,
    get_recent_messages_by_user,
    get_group_chat_by_chat_id,
    get_routing_config,
    list_message_batches,
    list_owner_role_map,
    get_signup_tag_rules_config,
    materialize_message_batches,
    record_conversion_feedback,
    resolve_person_identity,
    save_outbound_task,
    save_tag_snapshot,
    remove_tag_snapshot,
    search_messages,
)
from .wecom_client import WeComClient
from .mcp_chat_dump_service import build_owner_recent_chat_dump_payload
from .mcp_followup_service import build_followup_candidates_payload
from .mcp_tool_definitions import TOOL_DEFS

mcp_bp = Blueprint("mcp", __name__)
mcp_logger = logging.getLogger("mcp")


def _check_mcp_auth() -> Response | None:
    expected = str(request.environ.get("mcp_bearer_token_override") or "").strip()
    if not expected:
        from flask import current_app

        expected = str(current_app.config.get("MCP_BEARER_TOKEN", "") or "").strip()
    if not expected:
        return None
    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer "):
        return jsonify({"ok": False, "error": "missing bearer token"}), 401
    token = auth_header[7:].strip()
    if token != expected:
        return jsonify({"ok": False, "error": "invalid bearer token"}), 401
    return None


def _tool_result(payload: Any) -> dict[str, Any]:
    payload = _json_safe(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
    }


def _tool_result_messages(messages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"messages": _json_safe(messages)}
    for key, value in extra.items():
        payload[key] = _json_safe(value)
    return _tool_result(payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    return value


def _jsonrpc_success(request_id: Any, result: dict[str, Any]) -> Response:
    return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})


def _jsonrpc_error(request_id: Any, code: int, message: str) -> Response:
    return jsonify({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})




def _normalize_customer_ref(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = re.sub(r"[\s()\-]+", "", text)
    if compact.startswith("+86"):
        compact = compact[3:]
    elif compact.startswith("86") and len(compact) == 13:
        compact = compact[2:]
    if re.fullmatch(r"1\d{10}", compact):
        return compact
    return text


def _is_mobile_customer_ref(value: str) -> bool:
    return bool(re.fullmatch(r"1\d{10}", value))


def _resolve_customer_locator(arguments: dict[str, Any], *, required: bool = True) -> dict[str, Any]:
    explicit_external_userid = str(arguments.get("external_userid") or "").strip()
    customer_ref = _normalize_customer_ref(arguments.get("customer_ref"))
    if explicit_external_userid:
        return {
            "customer_ref": customer_ref or explicit_external_userid,
            "matched_by": "external_userid",
            "external_userid": explicit_external_userid,
            "identity": resolve_person_identity(external_userid=explicit_external_userid),
        }
    if not customer_ref:
        if required:
            raise ValueError("customer_ref or external_userid is required")
        return {
            "customer_ref": "",
            "matched_by": "",
            "external_userid": "",
            "identity": {},
        }
    if _is_mobile_customer_ref(customer_ref):
        identity = resolve_person_identity(mobile=customer_ref)
        external_userid = str(identity.get("external_userid") or "").strip()
        if not external_userid:
            raise ValueError(f"customer not found for mobile: {customer_ref}")
        return {
            "customer_ref": customer_ref,
            "matched_by": "mobile",
            "external_userid": external_userid,
            "identity": identity,
        }
    return {
        "customer_ref": customer_ref,
        "matched_by": "external_userid",
        "external_userid": customer_ref,
        "identity": resolve_person_identity(external_userid=customer_ref),
    }


def _require_customer_detail(external_userid: str) -> dict[str, Any]:
    customer = get_customer_detail(external_userid)
    if not customer:
        raise ValueError("customer not found")
    return customer


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_limit(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        limit = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    return max(minimum, min(limit, maximum))


def _normalize_boolean(value: Any, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"{field_name} must be a boolean")


def _normalize_lookback_minutes(value: Any) -> int:
    try:
        lookback_minutes = int(value if value is not None else 60)
    except (TypeError, ValueError) as exc:
        raise ValueError("lookback_minutes must be an integer") from exc
    return max(1, min(lookback_minutes, 1440))


def _require_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _collect_customer_refs(arguments: dict[str, Any]) -> list[str]:
    refs = _normalize_string_list(arguments.get("customer_refs"))
    refs.extend(item for item in _normalize_string_list(arguments.get("external_userids")) if item not in refs)
    if refs:
        return refs

    single_ref = (
        str(arguments.get("customer_ref") or "").strip()
        or str(arguments.get("external_userid") or "").strip()
    )
    return [single_ref] if single_ref else []


def _resolve_customers(arguments: dict[str, Any], *, allow_multiple: bool) -> list[dict[str, Any]]:
    refs = _collect_customer_refs(arguments)
    if not refs:
        raise ValueError("customer_ref or external_userid is required")
    if not allow_multiple and len(refs) != 1:
        raise ValueError("exactly one customer_ref is required")

    resolved: list[dict[str, Any]] = []
    seen_external_userids: set[str] = set()
    for ref in refs:
        locator_arguments = {"customer_ref": ref}
        locator = _resolve_customer_locator(locator_arguments)
        external_userid = locator["external_userid"]
        if external_userid in seen_external_userids:
            continue
        seen_external_userids.add(external_userid)
        resolved.append(
            {
                "customer_ref": ref,
                "matched_by": locator["matched_by"],
                "external_userid": external_userid,
                "identity": locator["identity"],
                "customer": _require_customer_detail(external_userid),
            }
        )
    return resolved


def _resolve_sender_userids(customers: list[dict[str, Any]], explicit_userid: Any = "") -> list[str]:
    explicit = str(explicit_userid or "").strip()
    if explicit:
        return [explicit]

    userids: list[str] = []
    seen: set[str] = set()
    for item in customers:
        owner_userid = str((item.get("customer") or {}).get("owner_userid") or "").strip()
        if not owner_userid or owner_userid in seen:
            continue
        seen.add(owner_userid)
        userids.append(owner_userid)
    if userids:
        return userids
    raise ValueError("userid is required because no owner_userid could be resolved")









def _build_owner_recent_chat_dump(arguments: dict[str, Any]) -> dict[str, Any]:
    return build_owner_recent_chat_dump_payload(
        arguments,
        require_text=_require_text,
        normalize_lookback_minutes=_normalize_lookback_minutes,
        normalize_boolean=_normalize_boolean,
        get_db=get_db,
        get_group_chat_map=get_group_chat_map,
        extract_roomid_from_raw_payload=extract_roomid_from_raw_payload,
        format_message_row=format_message_row,
        get_contact_by_external_userid=get_contact_by_external_userid,
    )


def _build_followup_candidates(arguments: dict[str, Any]) -> dict[str, Any]:
    return build_followup_candidates_payload(
        arguments,
        normalize_limit=_normalize_limit,
        get_db=get_db,
        get_customer_detail=get_customer_detail,
        get_recent_messages_by_user=get_recent_messages_by_user,
    )

def _build_customer_context_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_customers(arguments, allow_multiple=False)[0]
    external_userid = resolved["external_userid"]
    refresh_tags = bool(arguments.get("refresh_tags"))
    recent_message_limit = _normalize_limit(arguments.get("recent_message_limit"), default=20, minimum=1, maximum=200)
    timeline_limit = _normalize_limit(arguments.get("timeline_limit"), default=20, minimum=1, maximum=200)
    customer = get_customer_detail(external_userid, refresh_tags=refresh_tags)
    timeline, degraded, warnings = _get_customer_timeline_payload(external_userid, timeline_limit)
    return {
        "ok": True,
        "customer_ref": resolved["customer_ref"],
        "matched_by": resolved["matched_by"],
        "external_userid": external_userid,
        "customer": customer or resolved["customer"],
        "recent_messages": get_recent_messages_by_user(external_userid, recent_message_limit),
        "timeline": timeline,
        "recent_timeline_events": timeline.get("items", []),
        "source_status": "live",
        "degraded": degraded,
        "warnings": warnings,
        "refresh_tags": refresh_tags,
    }


def _normalize_tag_arguments(arguments: dict[str, Any]) -> tuple[list[str], list[str]]:
    add_tags = _normalize_string_list(arguments.get("add_tags"))
    if not add_tags:
        add_tags = _normalize_string_list(arguments.get("add_tag"))
    remove_tags = _normalize_string_list(arguments.get("remove_tags"))
    if not remove_tags:
        remove_tags = _normalize_string_list(arguments.get("remove_tag"))
    if not add_tags and not remove_tags:
        raise ValueError("at least one of add_tags/remove_tags is required")
    return add_tags, remove_tags


def _run_tag_operation(operation: Any) -> dict[str, Any]:
    try:
        payload = operation()
    except Exception as exc:  # pragma: no cover - exact exception type depends on WeCom/API path
        return {
            "ok": False,
            "error": str(exc),
            "error_type": exc.__class__.__name__,
        }
    return {
        "ok": True,
        "response": payload,
    }


def _update_customer_tags(arguments: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_customers(arguments, allow_multiple=False)[0]
    add_tags, remove_tags = _normalize_tag_arguments(arguments)
    sender_userid = _resolve_sender_userids([resolved], arguments.get("userid"))[0]
    external_userid = resolved["external_userid"]
    client = WeComClient.from_app()

    result: dict[str, Any] = {
        "ok": True,
        "external_userid": external_userid,
        "userid": sender_userid,
        "add_tags": add_tags,
        "remove_tags": remove_tags,
        "results": {},
    }

    if add_tags:
        result["results"]["mark"] = _run_tag_operation(
            lambda: client.mark_tag(
                {
                    "userid": sender_userid,
                    "external_userid": external_userid,
                    "add_tag": add_tags,
                }
            )
        )
        if result["results"]["mark"]["ok"]:
            save_tag_snapshot(sender_userid, external_userid, add_tags)

    if remove_tags:
        result["results"]["unmark"] = _run_tag_operation(
            lambda: client.mark_tag(
                {
                    "userid": sender_userid,
                    "external_userid": external_userid,
                    "remove_tag": remove_tags,
                }
            )
        )
        if result["results"]["unmark"]["ok"]:
            remove_tag_snapshot(sender_userid, external_userid, remove_tags)

    result["ok"] = all(item["ok"] for item in result["results"].values())
    return result


def _build_private_message_payload(customers: list[dict[str, Any]], *, content: str, userid: Any = "") -> tuple[dict[str, Any], list[str]]:
    sender_userids = _resolve_sender_userids(customers, userid)
    payload = {
        "chat_type": "single",
        "external_userid": [customers[0]["external_userid"]],
        "sender": sender_userids,
        "text": {"content": content},
    }
    return payload, sender_userids


def _build_group_message_payload(customers: list[dict[str, Any]], *, content: str, userid: Any = "") -> tuple[dict[str, Any], list[str]]:
    sender_userids = _resolve_sender_userids(customers, userid)
    payload = {
        "chat_type": "group",
        "external_userid": [item["external_userid"] for item in customers],
        "sender": sender_userids,
        "text": {"content": content},
    }
    return payload, sender_userids


def _build_moment_payload(customers: list[dict[str, Any]], *, content: str, userid: Any = "") -> tuple[dict[str, Any], list[str]]:
    sender_userids = _resolve_sender_userids(customers, userid)
    payload = {
        "visible_range": {"sender_list": {"userid": sender_userids}},
        "text": {"content": content},
    }
    return payload, sender_userids


def _build_task_result(
    task_result: dict[str, Any],
    *,
    task_type: str,
    customers: list[dict[str, Any]],
    sender_userids: list[str],
) -> dict[str, Any]:
    external_userids = [item["external_userid"] for item in customers]
    return {
        "ok": True,
        "task_type": task_type,
        "task_id": task_result["task_id"],
        "wecom_result": task_result["wecom_result"],
        "external_userid": external_userids[0] if len(external_userids) == 1 else "",
        "external_userids": external_userids,
        "userid": sender_userids[0] if len(sender_userids) == 1 else "",
        "userids": sender_userids,
        "resolved_customers": [
            {
                "customer_ref": item["customer_ref"],
                "matched_by": item["matched_by"],
                "external_userid": item["external_userid"],
                "customer_name": str((item.get("customer") or {}).get("customer_name") or "").strip(),
                "owner_userid": str((item.get("customer") or {}).get("owner_userid") or "").strip(),
            }
            for item in customers
        ],
    }


def _default_timeline_payload(external_userid: str, timeline_limit: int) -> dict[str, Any]:
    return {
        "external_userid": external_userid,
        "items": [],
        "count": 0,
        "limit": timeline_limit,
        "offset": 0,
        "filters": {"event_type": "", "limit": str(timeline_limit), "offset": "0"},
        "total": 0,
    }


def _normalize_timeline_payload(
    timeline: Any,
    *,
    external_userid: str,
    timeline_limit: int,
    compatibility_mode: bool,
) -> tuple[dict[str, Any], bool]:
    if not isinstance(timeline, dict):
        return _default_timeline_payload(external_userid, timeline_limit), True
    items = timeline.get("items")
    if not isinstance(items, list):
        items = []
    if compatibility_mode:
        items = items[:timeline_limit]
    normalized = dict(timeline)
    normalized["external_userid"] = str(timeline.get("external_userid") or external_userid).strip() or external_userid
    normalized["items"] = items
    normalized["count"] = len(items)
    normalized["limit"] = int(timeline.get("limit") or timeline_limit)
    normalized["offset"] = int(timeline.get("offset") or 0)
    normalized["filters"] = timeline.get("filters") or {
        "event_type": "",
        "limit": str(timeline_limit),
        "offset": "0",
    }
    normalized["total"] = int(timeline.get("total") or len(items))
    return normalized, False


def _get_customer_timeline_payload(external_userid: str, timeline_limit: int) -> tuple[dict[str, Any], bool, list[str]]:
    filters = {
        "normalized_limit": timeline_limit,
        "normalized_offset": 0,
        "limit": timeline_limit,
        "offset": 0,
        "event_type": "",
    }
    warnings: list[str] = []
    try:
        timeline = get_customer_timeline(external_userid, filters)
        normalized, fallback_failed = _normalize_timeline_payload(
            timeline,
            external_userid=external_userid,
            timeline_limit=timeline_limit,
            compatibility_mode=False,
        )
        return normalized, fallback_failed, warnings
    except TypeError as exc:
        message = str(exc)
        if "positional argument" not in message:
            raise
        warnings.append("timeline compatibility fallback applied: legacy get_customer_timeline signature")
        timeline = get_customer_timeline(external_userid)  # type: ignore[misc]
        normalized, fallback_failed = _normalize_timeline_payload(
            timeline,
            external_userid=external_userid,
            timeline_limit=timeline_limit,
            compatibility_mode=True,
        )
        return normalized, fallback_failed, warnings


def _parse_dry_run(arguments: dict[str, Any]) -> bool:
    dry_run = arguments.get("dry_run")
    if dry_run is None:
        return True
    if isinstance(dry_run, bool):
        return dry_run
    text = str(dry_run).strip().lower()
    if text in {"", "1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError("dry_run must be a boolean")


def _parse_confirm(arguments: dict[str, Any]) -> bool:
    confirm = arguments.get("confirm")
    if isinstance(confirm, bool):
        return confirm
    text = str(confirm or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def _build_task_preview_result(
    *,
    task_type: str,
    customers: list[dict[str, Any]],
    sender_userids: list[str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    resolved_customers = [
        {
            "customer_ref": item["customer_ref"],
            "matched_by": item["matched_by"],
            "external_userid": item["external_userid"],
            "customer_name": str((item.get("customer") or {}).get("customer_name") or "").strip(),
            "owner_userid": str((item.get("customer") or {}).get("owner_userid") or "").strip(),
        }
        for item in customers
    ]
    resolved_external_userids = [item["external_userid"] for item in customers]
    resolved_owner_userids = [userid for userid in sender_userids if userid]
    result: dict[str, Any] = {
        "ok": True,
        "task_type": task_type,
        "dry_run": True,
        "would_execute": True,
        "preview_payload": payload,
        "resolved_customers": resolved_customers,
        "resolved_external_userids": resolved_external_userids,
        "resolved_owner_userids": resolved_owner_userids,
    }
    if len(resolved_customers) == 1:
        result["resolved_customer"] = resolved_customers[0]
    return result


def _call_business_task(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    business_mode = bool(_collect_customer_refs(arguments) or str(arguments.get("content") or "").strip())
    dry_run = _parse_dry_run(arguments)
    confirm = _parse_confirm(arguments)
    if not dry_run and not confirm:
        raise ValueError("confirm=true is required when dry_run=false")
    if not business_mode:
        mapping = {
            "create_private_message_task": ("create_private_message_task", "private_message"),
            "create_group_message_task": ("create_group_message_task", "group_message"),
            "create_moment_task": ("create_moment_task", "moment"),
        }
        fn_name, task_type = mapping[name]
        if dry_run:
            return _tool_result(
                {
                    "ok": True,
                    "task_type": task_type,
                    "dry_run": True,
                    "would_execute": True,
                    "preview_payload": arguments,
                    "resolved_customers": [],
                    "resolved_external_userids": _normalize_string_list(arguments.get("external_userids") or arguments.get("external_userid")),
                    "resolved_owner_userids": _normalize_string_list(arguments.get("sender") or arguments.get("userid")),
                }
            )
        return _tool_result(_call_wecom_task(fn_name, task_type, arguments))

    content = _require_text(arguments.get("content"), field_name="content")
    if name == "create_private_message_task":
        customers = _resolve_customers(arguments, allow_multiple=False)
        payload, sender_userids = _build_private_message_payload(customers, content=content, userid=arguments.get("userid"))
        if dry_run:
            return _tool_result(
                _build_task_preview_result(
                    task_type="private_message",
                    customers=customers,
                    sender_userids=sender_userids,
                    payload=payload,
                )
            )
        task_result = _call_wecom_task("create_private_message_task", "private_message", payload)
        return _tool_result(_build_task_result(task_result, task_type="private_message", customers=customers, sender_userids=sender_userids))
    if name == "create_group_message_task":
        customers = _resolve_customers(arguments, allow_multiple=True)
        payload, sender_userids = _build_group_message_payload(customers, content=content, userid=arguments.get("userid"))
        if dry_run:
            return _tool_result(
                _build_task_preview_result(
                    task_type="group_message",
                    customers=customers,
                    sender_userids=sender_userids,
                    payload=payload,
                )
            )
        task_result = _call_wecom_task("create_group_message_task", "group_message", payload)
        return _tool_result(_build_task_result(task_result, task_type="group_message", customers=customers, sender_userids=sender_userids))
    if name == "create_moment_task":
        customers = _resolve_customers(arguments, allow_multiple=True)
        payload, sender_userids = _build_moment_payload(customers, content=content, userid=arguments.get("userid"))
        if dry_run:
            return _tool_result(
                _build_task_preview_result(
                    task_type="moment",
                    customers=customers,
                    sender_userids=sender_userids,
                    payload=payload,
                )
            )
        task_result = _call_wecom_task("create_moment_task", "moment", payload)
        return _tool_result(_build_task_result(task_result, task_type="moment", customers=customers, sender_userids=sender_userids))
    raise ValueError(f"unknown business task: {name}")








def _call_wecom_task(fn_name: str, task_type: str, arguments: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = getattr(client, fn_name)(arguments)
    local_id = save_outbound_task(task_type, arguments, result)
    return {"ok": True, "task_id": local_id, "wecom_result": result}


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    arguments = arguments or {}
    if name == "resolve_customer":
        payload = _build_customer_context_payload(arguments) if bool(arguments.get("include_context")) else {}
        if not payload:
            resolved = _resolve_customers(arguments, allow_multiple=False)[0]
            payload = {
                "ok": True,
                "customer_ref": resolved["customer_ref"],
                "matched_by": resolved["matched_by"],
                "external_userid": resolved["external_userid"],
                "customer": resolved["customer"],
            }
        payload["available_actions"] = [
            "get_customer_context",
            "get_contact",
            "get_messages",
            "get_recent_messages",
            "search_messages",
            "update_customer_tags",
            "mark_tags",
            "unmark_tags",
            "create_private_message_task",
            "create_group_message_task",
            "create_moment_task",
        ]
        return _tool_result(payload)
    if name == "get_contact":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        return _tool_result(
            get_contact_by_external_userid(external_userid, refresh_tags=bool(arguments.get("refresh_tags"))) or {}
        )
    if name == "get_customer_context":
        return _tool_result(_build_customer_context_payload(arguments))
    if name == "get_messages":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        return _tool_result_messages(
            get_messages_by_user(
                external_userid,
                chat_type=arguments.get("chat_type"),
            ),
            external_userid=external_userid,
            chat_type=(arguments.get("chat_type") or "").strip(),
        )
    if name == "get_recent_messages":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        limit = int(arguments.get("limit", 20))
        return _tool_result_messages(
            get_recent_messages_by_user(
                external_userid,
                limit,
                chat_type=arguments.get("chat_type"),
            ),
            external_userid=external_userid,
            limit=limit,
            chat_type=(arguments.get("chat_type") or "").strip(),
        )
    if name == "search_messages":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        keyword = (arguments.get("keyword") or "").strip()
        return _tool_result_messages(
            search_messages(
                external_userid,
                keyword,
            ),
            external_userid=external_userid,
            keyword=keyword,
        )
    if name == "get_group_chat":
        chat_id = (arguments.get("chat_id") or "").strip()
        if not chat_id:
            raise ValueError("chat_id is required")
        return _tool_result(get_group_chat_by_chat_id(chat_id) or {})
    if name == "update_customer_tags":
        return _tool_result(_update_customer_tags(arguments))
    if name == "mark_tags":
        result = _update_customer_tags(arguments)
        return _tool_result({"ok": result["ok"], "result": result["results"].get("mark")})
    if name == "unmark_tags":
        result = _update_customer_tags(arguments)
        return _tool_result({"ok": result["ok"], "result": result["results"].get("unmark")})
    if name == "create_private_message_task":
        return _call_business_task(name, arguments)
    if name == "create_moment_task":
        return _call_business_task(name, arguments)
    if name == "create_group_message_task":
        return _call_business_task(name, arguments)
    if name == "record_conversion_feedback":
        locator = _resolve_customer_locator(arguments, required=False)
        feedback_id = record_conversion_feedback(
            feedback_type=(arguments.get("feedback_type") or "").strip(),
            external_userid=locator["external_userid"],
            chat_id=(arguments.get("chat_id") or "").strip(),
            actor=(arguments.get("actor") or "").strip(),
            feedback_payload=arguments.get("feedback_payload") or {},
        )
        return _tool_result({"ok": True, "feedback_id": feedback_id})
    if name == "get_owner_role_map":
        return _tool_result(
            {
                "items": list_owner_role_map(active_only=bool(arguments.get("active_only", False))),
            }
        )
    if name == "get_signup_tag_rules":
        return _tool_result(get_signup_tag_rules_config())
    if name == "get_routing_config":
        return _tool_result(get_routing_config())
    if name == "get_owner_recent_chat_dump":
        return _tool_result(_build_owner_recent_chat_dump(arguments))
    if name == "get_pending_message_batches":
        materialize_message_batches(window_minutes=3)
        return _tool_result(
            list_message_batches(
                limit=int(arguments.get("limit", 20)),
                cursor=str(arguments.get("cursor", "") or ""),
            )
        )
    if name == "get_message_batch":
        materialize_message_batches(window_minutes=3)
        batch = get_message_batch(
            int(arguments.get("batch_id", 0)),
            limit=int(arguments.get("limit", 200)),
            cursor=str(arguments.get("cursor", "") or ""),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "ack_message_batch":
        batch = ack_message_batch(
            int(arguments.get("batch_id", 0)),
            ack_note=(arguments.get("ack_note") or ""),
            acked_by=(arguments.get("acked_by") or ""),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "get_hourly_followup_candidates":
        return _tool_result(_build_followup_candidates(arguments))
    raise ValueError(f"unknown tool: {name}")


@mcp_bp.route("/mcp", methods=["GET", "POST"])
def streamable_http_mcp():
    auth_error = _check_mcp_auth()
    if auth_error is not None:
        return auth_error
    if request.method == "GET":
        return jsonify(
            {
                "ok": True,
                "transport": "streamable-http",
                "mcp_endpoint": "/mcp",
                "server_name": "openclaw-wecom-mcp",
            }
        )

    payload = request.get_json(silent=True) or {}
    request_id = payload.get("id")
    method = payload.get("method", "")
    params = payload.get("params") or {}
    mcp_logger.info("mcp method=%s", method)

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "openclaw-wecom-mcp", "version": "1.0.0"},
            }
            return _jsonrpc_success(request_id, result)
        if method == "notifications/initialized":
            return Response(status=204)
        if method == "tools/list":
            return _jsonrpc_success(request_id, {"tools": TOOL_DEFS})
        if method == "tools/call":
            result = _call_tool(params.get("name", ""), params.get("arguments") or {})
            return _jsonrpc_success(request_id, result)
        if method == "ping":
            return _jsonrpc_success(request_id, {})
        return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        mcp_logger.exception("mcp call failed method=%s", method)
        return _jsonrpc_error(request_id, -32000, str(exc))