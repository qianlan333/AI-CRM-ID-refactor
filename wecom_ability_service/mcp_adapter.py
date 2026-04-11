from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

from flask import Blueprint, Response, jsonify, request

from .customer_center import get_customer_detail
from .customer_timeline.service import get_customer_timeline
from .db import get_db
from .domains.admin_config import list_mcp_runtime_tools, mcp_tool_enabled
from .domains.automation_conversion import (
    audit_agent_skill_call,
    create_agent_output_export_job,
    get_agent_config_detail,
    get_agent_output_detail,
    get_agent_output_export_job,
    get_agent_outputs_by_request,
    get_agent_outputs_by_user,
    get_pool_snapshot,
    list_agent_outputs,
    save_agent_config_draft,
    suggest_pool_action,
)
from .http.internal_auth import require_internal_api_token
from .services import (
    ack_conversion_batch,
    ack_message_batch,
    extract_roomid_from_raw_payload,
    format_message_row,
    get_contact_by_external_userid,
    get_conversion_batch,
    get_group_chat_map,
    get_message_batch,
    get_messages_by_user,
    get_openclaw_customer_marketing_profile,
    get_pending_conversion_batches,
    get_signup_conversion_batch,
    get_recent_messages_by_user,
    get_group_chat_by_chat_id,
    get_routing_config,
    list_signup_conversion_batches,
    list_message_batches,
    list_owner_role_map,
    mark_enrolled,
    get_signup_tag_rules_config,
    materialize_message_batches,
    record_conversion_feedback,
    resolve_person_identity,
    save_outbound_task,
    save_tag_snapshot,
    send_pool_private_message,
    remove_tag_snapshot,
    search_messages,
    unmark_enrolled,
)
from .wecom_client import WeComClient

mcp_bp = Blueprint("mcp", __name__)
mcp_logger = logging.getLogger("mcp")


def _check_mcp_auth() -> Response | None:
    expected = str(request.environ.get("mcp_bearer_token_override") or "").strip()
    if not expected:
        return require_internal_api_token(token_keys=("MCP_BEARER_TOKEN",))
    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer "):
        return jsonify({"ok": False, "error": "missing internal token"}), 401
    token = auth_header[7:].strip()
    if token != expected:
        return jsonify({"ok": False, "error": "invalid internal token"}), 401
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


def get_mcp_http_info() -> dict[str, Any]:
    return {
        "ok": True,
        "transport": "streamable-http",
        "mcp_endpoint": "/mcp",
        "server_name": "openclaw-wecom-mcp",
    }


def initialize_mcp_runtime() -> dict[str, Any]:
    return {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "openclaw-wecom-mcp", "version": "1.0.0"},
    }


TOOL_DEFS = [
    {
        "name": "resolve_customer",
        "description": "Resolve customer_ref (mobile or external_userid) to a CRM customer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "include_context": {"type": "boolean"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_contact",
        "description": "Read a single contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "refresh_tags": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_customer_context",
        "description": "Read a customer's aggregated CRM context by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "refresh_tags": {"type": "boolean"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_messages",
        "description": "Read full message history for a contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "chat_type": {"type": "string", "enum": ["private", "group"]},
            },
        },
    },
    {
        "name": "get_recent_messages",
        "description": "Read recent messages for a contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "chat_type": {"type": "string", "enum": ["private", "group"]},
            },
        },
    },
    {
        "name": "search_messages",
        "description": "Search messages for a contact by keyword, using customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "keyword": {"type": "string"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_group_chat",
        "description": "Read a group chat by chat_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
            },
            "required": ["chat_id"],
        },
    },
    {
        "name": "mark_tags",
        "description": "Add one or more tags to a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "add_tag": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["userid", "add_tag"],
        },
    },
    {
        "name": "unmark_tags",
        "description": "Remove one or more tags from a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "remove_tag": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["userid", "remove_tag"],
        },
    },
    {
        "name": "update_customer_tags",
        "description": "Update a customer's tags with customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "userid": {"type": "string"},
                "add_tags": {"type": "array", "items": {"type": "string"}},
                "remove_tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "create_private_message_task",
        "description": "Create a private message task using a simple business input or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "create_moment_task",
        "description": "Create a moment task using customer_ref/customer_refs or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "customer_refs": {"type": "array", "items": {"type": "string"}},
                "external_userid": {"type": "string"},
                "external_userids": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "create_group_message_task",
        "description": "Create a group message task using customer_ref/customer_refs or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "customer_refs": {"type": "array", "items": {"type": "string"}},
                "external_userid": {"type": "string"},
                "external_userids": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "send_pool_private_message",
        "description": "Send one private-message batch directly to one CRM pool. Supports text, images, attachments, or mixed combinations; CRM filters the pool, sends, and writes send records.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_userid": {"type": "string"},
                "pool_key": {
                    "type": "string",
                    "enum": ["new_user", "inactive_normal", "inactive_focus", "active_normal", "active_focus", "silent"],
                },
                "content": {"type": "string"},
                "images": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "file_name": {"type": "string"},
                                    "content_type": {"type": "string"},
                                    "data_url": {"type": "string"},
                                    "data_base64": {"type": "string"},
                                    "media_id": {"type": "string"},
                                },
                            },
                        ]
                    },
                },
                "image_media_ids": {"type": "array", "items": {"type": "string"}},
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "msgtype": {
                                "type": "string",
                                "enum": ["file"],
                            },
                            "file": {"type": "object"},
                        },
                        "required": ["msgtype"],
                    },
                },
                "confirm": {"type": "boolean"},
                "operator": {"type": "string"},
            },
            "required": ["owner_userid", "pool_key", "confirm"],
        },
    },
    {
        "name": "record_conversion_feedback",
        "description": "Persist conversion feedback from OpenClaw; mark_enrolled/unmark_enrolled feedback types also sync unified conversion truth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feedback_type": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "chat_id": {"type": "string"},
                "actor": {"type": "string"},
                "feedback_payload": {"type": "object"},
            },
            "required": ["feedback_type"],
        },
    },
    {
        "name": "get_owner_role_map",
        "description": "Read the owner role mapping used for routing validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_signup_tag_rules",
        "description": "Read signup tag rules used for pre/post-signup routing validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_routing_config",
        "description": "Read both owner role map and signup tag rules in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_pending_message_batches",
        "description": "List pending 3-minute message batches for OpenClaw to judge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_message_batch",
        "description": "Fetch a batch with full message payloads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "cursor": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "ack_message_batch",
        "description": "Acknowledge a batch after OpenClaw has consumed it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "ack_note": {"type": "string"},
                "acked_by": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_signup_conversion_batches",
        "description": "List pending message batches that remain eligible for signup-conversion automation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_customer_marketing_profile",
        "description": "Read one CRM-organized marketing profile for OpenClaw without combining customer detail manually.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_userid": {"type": "string"},
                "person_id": {"type": "integer"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "get_pending_conversion_batches",
        "description": "List only the pending conversion batches that have router-approved candidates for OpenClaw.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_conversion_batch",
        "description": "Fetch one OpenClaw-ready conversion batch with CRM-organized marketing profiles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "ack_conversion_batch",
        "description": "Acknowledge a conversion batch after OpenClaw has consumed it and stamp acked_at in dispatch logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "ack_note": {"type": "string"},
                "acked_by": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_signup_conversion_batch",
        "description": "Fetch one filtered signup-conversion batch with CRM-organized customer profiles for OpenClaw.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "mark_enrolled",
        "description": "Mark one customer as enrolled through the unified CRM conversion service.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_userid": {"type": "string"},
                "owner_userid": {"type": "string"},
                "operator": {"type": "string"},
                "source": {"type": "string"},
                "signup_status": {"type": "string"},
            },
            "required": ["external_userid"],
        },
    },
    {
        "name": "unmark_enrolled",
        "description": "Undo one enrolled mark and recompute the customer's stage from CRM facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_userid": {"type": "string"},
                "owner_userid": {"type": "string"},
                "operator": {"type": "string"},
                "source": {"type": "string"},
                "restore_signup_status": {"type": "string"},
            },
            "required": ["external_userid"],
        },
    },
    {
        "name": "get_owner_recent_chat_dump",
        "description": "Read recent private/group archived chat dumps for one owner without ranking or recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_userid": {"type": "string"},
                "lookback_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
                "include_private": {"type": "boolean"},
                "include_group": {"type": "boolean"},
            },
            "required": ["owner_userid"],
        },
    },
    {
        "name": "get_hourly_followup_candidates",
        "description": "List the best customers to follow up with right now using simple CRM rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "lookback_hours": {"type": "integer", "minimum": 1, "maximum": 168},
            },
        },
    },
    {
        "name": "get_pool_snapshot",
        "description": "Read a pool/stage snapshot for automation conversion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pool_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["pool_key"],
        },
    },
    {
        "name": "get_agent_config",
        "description": "Read one child agent's draft/published configuration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "save_agent_prompt_draft",
        "description": "Save one child agent's draft configuration without publishing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "display_name": {"type": "string"},
                "enabled": {"type": "boolean"},
                "role_prompt": {"type": "string"},
                "task_prompt": {"type": "string"},
                "variables": {"type": "array"},
                "output_schema": {"type": "array"},
                "change_summary": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code", "role_prompt", "task_prompt"],
        },
    },
    {
        "name": "list_agent_outputs",
        "description": "Query the unified agent output ledger with filters and pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object"},
                "page": {"type": "integer", "minimum": 1, "maximum": 100000},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "get_agent_output",
        "description": "Read one agent output record plus its run context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_id": {"type": "string"},
            },
            "required": ["output_id"],
        },
    },
    {
        "name": "get_agent_outputs_by_request",
        "description": "Read agent outputs by request_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
            },
            "required": ["request_id"],
        },
    },
    {
        "name": "get_agent_outputs_by_user",
        "description": "Read recent agent outputs by external_contact_id or userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["userid"],
        },
    },
    {
        "name": "export_agent_outputs",
        "description": "Create an Excel export job for agent outputs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object"},
                "requested_by": {"type": "string"},
            },
        },
    },
    {
        "name": "suggest_pool_action",
        "description": "Return a safe pool-action suggestion for one member without applying it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
                "operator": {"type": "string"},
            },
        },
    },
]


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


def _list_owner_archived_messages(
    owner_userid: str,
    *,
    window_start: str,
    window_end: str,
    include_private: bool,
    include_group: bool,
) -> list[dict[str, Any]]:
    if not include_private and not include_group:
        return []

    sql = """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE owner_userid = ? AND send_time >= ? AND send_time <= ?
    """
    params: list[Any] = [owner_userid, window_start, window_end]
    if include_private and not include_group:
        sql += " AND chat_type = ?"
        params.append("private")
    elif include_group and not include_private:
        sql += " AND chat_type = ?"
        params.append("group")
    sql += " ORDER BY send_time ASC, id ASC"
    return get_db().execute(sql, tuple(params)).fetchall()


def _sender_role_for_message(message: dict[str, Any], *, owner_userid: str) -> str:
    sender = str(message.get("from") or message.get("sender") or "").strip()
    external_userid = str(message.get("external_userid") or "").strip()
    if sender and sender == owner_userid:
        return "staff"
    if sender and external_userid and sender == external_userid:
        return "customer"
    return "unknown"


def _build_owner_recent_chat_dump(arguments: dict[str, Any]) -> dict[str, Any]:
    owner_userid = _require_text(arguments.get("owner_userid"), field_name="owner_userid")
    lookback_minutes = _normalize_lookback_minutes(arguments.get("lookback_minutes"))
    include_private = _normalize_boolean(arguments.get("include_private"), field_name="include_private", default=True)
    include_group = _normalize_boolean(arguments.get("include_group"), field_name="include_group", default=True)

    window_end_dt = datetime.now()
    window_start_dt = window_end_dt - timedelta(minutes=lookback_minutes)
    window_start = window_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    window_end = window_end_dt.strftime("%Y-%m-%d %H:%M:%S")

    rows = _list_owner_archived_messages(
        owner_userid,
        window_start=window_start,
        window_end=window_end,
        include_private=include_private,
        include_group=include_group,
    )
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    formatted_messages = [format_message_row(row, group_map=group_map) for row in rows]

    private_conversations_by_userid: dict[str, dict[str, Any]] = {}
    group_conversations_by_chat_id: dict[str, dict[str, Any]] = {}
    contact_cache: dict[str, dict[str, Any]] = {}

    for message in formatted_messages:
        chat_type = str(message.get("chat_type") or "").strip().lower()
        if chat_type == "private":
            external_userid = str(message.get("external_userid") or "").strip()
            if not external_userid:
                continue
            contact = contact_cache.get(external_userid)
            if contact is None:
                contact = get_contact_by_external_userid(external_userid) or {}
                contact_cache[external_userid] = contact
            conversation = private_conversations_by_userid.setdefault(
                external_userid,
                {
                    "external_userid": external_userid,
                    "customer_name": str(contact.get("customer_name") or "").strip(),
                    "messages": [],
                },
            )
            conversation["messages"].append(
                {
                    "send_time": str(message.get("send_time") or "").strip(),
                    "sender_role": _sender_role_for_message(message, owner_userid=owner_userid),
                    "msgtype": str(message.get("msgtype") or "").strip(),
                    "content": str(message.get("content") or "").strip(),
                    "owner_userid": owner_userid,
                    "sender": str(message.get("sender") or "").strip(),
                    "from": str(message.get("from") or "").strip(),
                    "tolist": message.get("tolist") or [],
                }
            )
            continue

        if chat_type != "group":
            continue

        chat_id = str(message.get("roomid") or message.get("chat_id") or "").strip()
        conversation = group_conversations_by_chat_id.setdefault(
            chat_id,
            {
                "roomid": chat_id,
                "chat_id": chat_id,
                "group_name": str(message.get("group_name") or "").strip(),
                "messages": [],
            },
        )
        conversation["messages"].append(
            {
                "send_time": str(message.get("send_time") or "").strip(),
                "sender_role": _sender_role_for_message(message, owner_userid=owner_userid),
                "external_userid": str(message.get("external_userid") or "").strip(),
                "msgtype": str(message.get("msgtype") or "").strip(),
                "content": str(message.get("content") or "").strip(),
                "owner_userid": owner_userid,
                "sender": str(message.get("sender") or "").strip(),
                "from": str(message.get("from") or "").strip(),
                "tolist": message.get("tolist") or [],
            }
        )

    return {
        "ok": True,
        "owner_userid": owner_userid,
        "lookback_minutes": lookback_minutes,
        "window_start": window_start,
        "window_end": window_end,
        "include_private": include_private,
        "include_group": include_group,
        "private_conversations": list(private_conversations_by_userid.values()),
        "group_conversations": list(group_conversations_by_chat_id.values()),
    }


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
        "sender": sender_userids[0] if sender_userids else "",
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


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _stringify_tags(customer: dict[str, Any]) -> list[str]:
    tags = customer.get("tags") or []
    result: list[str] = []
    seen: set[str] = set()
    for item in tags:
        if isinstance(item, dict):
            value = str(item.get("tag_name") or item.get("tag_id") or "").strip()
        else:
            value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    class_status = customer.get("class_user_status") or {}
    signup_label_name = str(class_status.get("signup_label_name") or "").strip()
    if signup_label_name and signup_label_name not in seen:
        result.append(signup_label_name)
    return result


def _build_followup_candidates(arguments: dict[str, Any]) -> dict[str, Any]:
    limit = _normalize_limit(arguments.get("limit"), default=20, minimum=1, maximum=100)
    lookback_hours = _normalize_limit(arguments.get("lookback_hours"), default=24, minimum=1, maximum=168)
    now = datetime.now()
    since = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = get_db().execute(
        """
        SELECT external_userid, MAX(send_time) AS last_message_at
        FROM archived_messages
        WHERE external_userid IS NOT NULL AND external_userid <> '' AND send_time >= ?
        GROUP BY external_userid
        ORDER BY last_message_at DESC, external_userid ASC
        """,
        (since,),
    ).fetchall()

    blocked_keywords = ("已成交", "成交", "勿扰", "关闭", "黑名单")
    high_intent_keywords = ("高意向", "待跟进", "已报价")
    candidates: list[dict[str, Any]] = []

    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        customer = get_customer_detail(external_userid)
        if not customer:
            continue

        tags = _stringify_tags(customer)
        class_status = customer.get("class_user_status") or {}
        status_text = " ".join(
            [
                str(class_status.get("signup_status") or "").strip(),
                str(class_status.get("signup_label_name") or "").strip(),
                " ".join(tags),
            ]
        )
        if any(keyword in status_text for keyword in blocked_keywords):
            continue

        recent_messages = get_recent_messages_by_user(external_userid, 20)
        if not recent_messages:
            continue

        score = 0
        reasons: list[str] = []
        last_customer_message_at: datetime | None = None
        latest_message_from_customer = False
        for index, message in enumerate(recent_messages):
            sender = str(message.get("from") or message.get("sender") or "").strip()
            send_time = _parse_timestamp(message.get("send_time"))
            if index == 0 and sender == external_userid:
                latest_message_from_customer = True
            if sender == external_userid and send_time is not None:
                last_customer_message_at = send_time
                break

        if last_customer_message_at is not None:
            age_hours = (now - last_customer_message_at).total_seconds() / 3600
            if age_hours <= 1:
                score += 5
                reasons.append("最近1小时客户有消息")
            elif age_hours <= 6:
                score += 3
                reasons.append("最近6小时客户有消息")

        if latest_message_from_customer:
            score += 4
            reasons.append("客户最后一条消息后暂无顾问跟进")

        if any(keyword in tag for tag in tags for keyword in high_intent_keywords):
            score += 3
            reasons.append("当前标签包含高意向信号")

        score += 2
        reasons.append("客户仍处于可继续跟进状态")

        if score <= 0:
            continue

        candidates.append(
            {
                "external_userid": external_userid,
                "customer_name": str(customer.get("customer_name") or "").strip(),
                "owner_userid": str(customer.get("owner_userid") or "").strip(),
                "score": score,
                "reason": reasons[0],
                "reasons": reasons,
                "suggested_action": "contact_now" if score >= 6 else "review_context",
                "last_message_at": str(customer.get("last_message_at") or row.get("last_message_at") or "").strip(),
                "tags": tags,
                "class_user_status": class_status,
            }
        )

    candidates.sort(key=lambda item: (int(item["score"]), str(item["last_message_at"]), item["external_userid"]), reverse=True)
    ranked = []
    for index, item in enumerate(candidates[:limit], start=1):
        payload = dict(item)
        payload["rank"] = index
        ranked.append(payload)

    return {
        "ok": True,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_hours": lookback_hours,
        "limit": limit,
        "candidates": ranked,
    }


def _call_wecom_task(fn_name: str, task_type: str, arguments: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = getattr(client, fn_name)(arguments)
    local_id = save_outbound_task(task_type, arguments, result)
    return {"ok": True, "task_id": local_id, "wecom_result": result}


def _run_agent_skill(
    skill_code: str,
    arguments: dict[str, Any],
    *,
    permission_scope: str,
    fn,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    idempotency_key = str(arguments.get("idempotency_key") or "").strip()
    try:
        payload = fn()
    except Exception as exc:
        audit_agent_skill_call(
            skill_code=skill_code,
            source="mcp",
            permissions_scope=permission_scope,
            request_payload=arguments,
            response_payload={"ok": False, "error": str(exc)},
            status="error",
            error_code="runtime_error",
            error_message=str(exc),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            idempotency_key=idempotency_key,
        )
        raise
    audit_agent_skill_call(
        skill_code=skill_code,
        source="mcp",
        permissions_scope=permission_scope,
        request_payload=arguments,
        response_payload=payload,
        status="success",
        latency_ms=int((time.perf_counter() - started_at) * 1000),
        idempotency_key=idempotency_key,
    )
    return _tool_result(payload)


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    arguments = arguments or {}
    if not mcp_tool_enabled(name):
        raise ValueError(f"tool is disabled: {name}")
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
            "send_pool_private_message",
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
    if name == "send_pool_private_message":
        return _tool_result(
            send_pool_private_message(
                owner_userid=str(arguments.get("owner_userid") or "").strip(),
                pool_key=str(arguments.get("pool_key") or "").strip(),
                content=str(arguments.get("content") or "").strip(),
                images=list(arguments.get("images") or []),
                image_media_ids=list(arguments.get("image_media_ids") or []),
                attachments=list(arguments.get("attachments") or []),
                confirm=bool(arguments.get("confirm")),
                operator=str(arguments.get("operator") or "").strip(),
            )
        )
    if name == "record_conversion_feedback":
        locator = _resolve_customer_locator(arguments, required=False)
        feedback_result = record_conversion_feedback(
            feedback_type=(arguments.get("feedback_type") or "").strip(),
            external_userid=locator["external_userid"],
            chat_id=(arguments.get("chat_id") or "").strip(),
            actor=(arguments.get("actor") or "").strip(),
            feedback_payload=arguments.get("feedback_payload") or {},
        )
        return _tool_result(feedback_result)
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
    if name == "get_signup_conversion_batches":
        return _tool_result(
            list_signup_conversion_batches(
                limit=int(arguments.get("limit", 20)),
                cursor=str(arguments.get("cursor", "") or ""),
            )
        )
    if name == "get_customer_marketing_profile":
        return _tool_result(
            get_openclaw_customer_marketing_profile(
                external_userid=str(arguments.get("external_userid") or "").strip(),
                person_id=arguments.get("person_id"),
                recent_message_limit=_normalize_limit(arguments.get("recent_message_limit"), default=3, minimum=1, maximum=50),
            )
        )
    if name == "get_pending_conversion_batches":
        return _tool_result(
            get_pending_conversion_batches(
                limit=int(arguments.get("limit", 20)),
                cursor=str(arguments.get("cursor", "") or ""),
            )
        )
    if name == "get_conversion_batch":
        batch = get_conversion_batch(
            int(arguments.get("batch_id", 0)),
            recent_message_limit=_normalize_limit(arguments.get("recent_message_limit"), default=3, minimum=1, maximum=50),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "ack_conversion_batch":
        batch = ack_conversion_batch(
            int(arguments.get("batch_id", 0)),
            ack_note=(arguments.get("ack_note") or ""),
            acked_by=(arguments.get("acked_by") or ""),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "get_signup_conversion_batch":
        batch = get_signup_conversion_batch(int(arguments.get("batch_id", 0)))
        if not batch:
            raise ValueError("batch not found")
        recent_message_limit = _normalize_limit(arguments.get("recent_message_limit"), default=20, minimum=1, maximum=200)
        timeline_limit = _normalize_limit(arguments.get("timeline_limit"), default=20, minimum=1, maximum=200)
        candidates: list[dict[str, Any]] = []
        for item in batch.get("candidates") or []:
            candidate = dict(item)
            external_userid = str(candidate.get("external_userid") or "").strip()
            if external_userid:
                candidate["customer_context"] = _build_customer_context_payload(
                    {
                        "external_userid": external_userid,
                        "recent_message_limit": recent_message_limit,
                        "timeline_limit": timeline_limit,
                    }
                )
            else:
                candidate["customer_context"] = {}
            candidates.append(candidate)
        batch["candidates"] = candidates
        return _tool_result(batch)
    if name == "mark_enrolled":
        return _tool_result(
            mark_enrolled(
                external_userid=str(arguments.get("external_userid") or "").strip(),
                owner_userid=str(arguments.get("owner_userid") or "").strip(),
                operator=str(arguments.get("operator") or "").strip(),
                source=str(arguments.get("source") or "").strip() or "mcp",
                signup_status=str(arguments.get("signup_status") or "").strip(),
            )
        )
    if name == "unmark_enrolled":
        return _tool_result(
            unmark_enrolled(
                external_userid=str(arguments.get("external_userid") or "").strip(),
                owner_userid=str(arguments.get("owner_userid") or "").strip(),
                operator=str(arguments.get("operator") or "").strip(),
                source=str(arguments.get("source") or "").strip() or "mcp",
                restore_signup_status=str(arguments.get("restore_signup_status") or "").strip(),
            )
        )
    if name == "get_hourly_followup_candidates":
        return _tool_result(_build_followup_candidates(arguments))
    if name == "get_pool_snapshot":
        return _run_agent_skill(
            "get_pool_snapshot",
            arguments,
            permission_scope="read",
            fn=lambda: get_pool_snapshot(
                pool_key=str(arguments.get("pool_key") or "").strip(),
                limit=int(arguments.get("limit") or 10),
            ),
        )
    if name == "get_agent_config":
        return _run_agent_skill(
            "get_agent_config",
            arguments,
            permission_scope="read",
            fn=lambda: {"agent": get_agent_config_detail(str(arguments.get("agent_code") or "").strip())},
        )
    if name == "save_agent_prompt_draft":
        return _run_agent_skill(
            "save_agent_prompt_draft",
            arguments,
            permission_scope="draft_write",
            fn=lambda: save_agent_config_draft(
                str(arguments.get("agent_code") or "").strip(),
                {
                    "display_name": arguments.get("display_name"),
                    "enabled": bool(arguments.get("enabled", True)),
                    "role_prompt": arguments.get("role_prompt"),
                    "task_prompt": arguments.get("task_prompt"),
                    "variables": list(arguments.get("variables") or []),
                    "output_schema": list(arguments.get("output_schema") or []),
                    "change_summary": arguments.get("change_summary"),
                },
                operator_id=str(arguments.get("operator") or "mcp").strip() or "mcp",
                source="mcp",
            ),
        )
    if name == "list_agent_outputs":
        return _run_agent_skill(
            "list_agent_outputs",
            arguments,
            permission_scope="read",
            fn=lambda: list_agent_outputs(
                dict(arguments.get("filters") or {}),
                page=int(arguments.get("page") or 1),
                page_size=int(arguments.get("page_size") or 20),
                visibility="full",
            ),
        )
    if name == "get_agent_output":
        return _run_agent_skill(
            "get_agent_output",
            arguments,
            permission_scope="read",
            fn=lambda: get_agent_output_detail(str(arguments.get("output_id") or "").strip(), visibility="full"),
        )
    if name == "get_agent_outputs_by_request":
        return _run_agent_skill(
            "list_agent_outputs",
            arguments,
            permission_scope="read",
            fn=lambda: get_agent_outputs_by_request(str(arguments.get("request_id") or "").strip(), visibility="full"),
        )
    if name == "get_agent_outputs_by_user":
        return _run_agent_skill(
            "list_agent_outputs",
            arguments,
            permission_scope="read",
            fn=lambda: get_agent_outputs_by_user(
                str(arguments.get("userid") or "").strip(),
                limit=int(arguments.get("limit") or 20),
                visibility="full",
            ),
        )
    if name == "export_agent_outputs":
        return _run_agent_skill(
            "export_agent_outputs",
            arguments,
            permission_scope="export",
            fn=lambda: {"job": create_agent_output_export_job(dict(arguments.get("filters") or {}), requested_by=str(arguments.get("requested_by") or "mcp").strip() or "mcp")},
        )
    if name == "suggest_pool_action":
        return _run_agent_skill(
            "suggest_pool_action",
            arguments,
            permission_scope="suggest_only",
            fn=lambda: suggest_pool_action(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
                operator_id=str(arguments.get("operator") or "mcp").strip() or "mcp",
            ),
        )
    raise ValueError(f"unknown tool: {name}")


def execute_mcp_tool_runtime(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return _call_tool(str(name or "").strip(), arguments or {})


@mcp_bp.route("/mcp", methods=["GET", "POST"])
def streamable_http_mcp():
    auth_error = _check_mcp_auth()
    if auth_error is not None:
        return auth_error
    if request.method == "GET":
        return jsonify(get_mcp_http_info())

    payload = request.get_json(silent=True) or {}
    request_id = payload.get("id")
    method = payload.get("method", "")
    params = payload.get("params") or {}
    mcp_logger.info("mcp method=%s", method)

    try:
        if method == "initialize":
            return _jsonrpc_success(request_id, initialize_mcp_runtime())
        if method == "notifications/initialized":
            return Response(status=204)
        if method == "tools/list":
            return _jsonrpc_success(request_id, {"tools": list_mcp_runtime_tools()})
        if method == "tools/call":
            result = execute_mcp_tool_runtime(params.get("name", ""), params.get("arguments") or {})
            return _jsonrpc_success(request_id, result)
        if method == "ping":
            return _jsonrpc_success(request_id, {})
        return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        mcp_logger.exception("mcp call failed method=%s", method)
        return _jsonrpc_error(request_id, -32000, str(exc))
