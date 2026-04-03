from __future__ import annotations

from typing import Any

from flask import current_app

from ...infra.constants import USER_OPS_CLASS_TERM_TAG_GROUP_NAME
from ...infra.settings import get_setting, mask_value
from ..routing_config import (
    OWNER_ROLE_OPTIONS,
    ROUTING_TARGET_OPTIONS,
    ensure_routing_rule_config_seed,
    get_owner_role,
    get_routing_rule,
    list_owner_role_map,
    list_routing_rules,
    save_owner_role_map_item,
    save_routing_rule_config_item,
)
from ..tags import service as tags_service
from ..user_ops import ensure_class_term_tag_mapping_seed
from . import repo

TARGET_OWNER_ROLE_MAP = "owner_role_map"
TARGET_ROUTING_RULE_CONFIG = "routing_rule_config"
TARGET_SIGNUP_TAG_RULE = "signup_tag_rule"
TARGET_CLASS_TERM_TAG_MAPPING = "class_term_tag_mapping"
TARGET_APP_SETTING = "app_setting"
TARGET_MCP_TOOL_SETTING = "mcp_tool_setting"

APP_SETTING_DEFINITIONS = (
    {
        "key": "WECOM_CORP_ID",
        "label": "WeCom Corp ID",
        "mode": "editable",
        "input_type": "text",
        "description": "企业微信 corp_id。",
    },
    {
        "key": "WECOM_AGENT_ID",
        "label": "WeCom Agent ID",
        "mode": "editable",
        "input_type": "text",
        "description": "企业微信应用 agent_id。",
    },
    {
        "key": "WECOM_API_BASE",
        "label": "WeCom API Base",
        "mode": "editable",
        "input_type": "url",
        "description": "企业微信 API 地址。",
    },
    {
        "key": "WECOM_DEFAULT_OWNER_USERID",
        "label": "Default Owner UserID",
        "mode": "editable",
        "input_type": "text",
        "description": "默认 owner userid。",
    },
    {
        "key": "WECOM_PRIVATE_KEY_PATH",
        "label": "Private Key Path",
        "mode": "editable",
        "input_type": "text",
        "description": "企微会话存档私钥路径。",
    },
    {
        "key": "WECOM_SDK_LIB_PATH",
        "label": "SDK Lib Path",
        "mode": "editable",
        "input_type": "text",
        "description": "企微会话存档 SDK 路径。",
    },
    {
        "key": "WECOM_ARCHIVE_TIMEOUT",
        "label": "Archive Timeout",
        "mode": "editable",
        "input_type": "number",
        "description": "企微 API 超时时间（秒）。",
    },
    {
        "key": "WECHAT_MP_APP_ID",
        "label": "WeChat MP App ID",
        "mode": "editable",
        "input_type": "text",
        "description": "微信 H5 OAuth app_id。",
    },
    {
        "key": "WECHAT_MP_OAUTH_SCOPE",
        "label": "WeChat OAuth Scope",
        "mode": "editable",
        "input_type": "text",
        "description": "微信 OAuth scope。",
    },
    {
        "key": "WECOM_SECRET",
        "label": "WeCom Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "企业微信主应用 secret。只展示掩码，留空则保持不变。",
    },
    {
        "key": "WECOM_CONTACT_SECRET",
        "label": "WeCom Contact Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "企业微信通讯录 secret。只展示掩码，留空则保持不变。",
    },
    {
        "key": "WECOM_ARCHIVE_SECRET",
        "label": "WeCom Archive Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "企业微信会话存档 secret。只展示掩码，留空则保持不变。",
    },
    {
        "key": "WECOM_CALLBACK_TOKEN",
        "label": "Callback Token",
        "mode": "masked",
        "input_type": "password",
        "description": "回调 token。只展示掩码，留空则保持不变。",
    },
    {
        "key": "WECOM_CALLBACK_AES_KEY",
        "label": "Callback AES Key",
        "mode": "masked",
        "input_type": "password",
        "description": "回调 AES key。只展示掩码，留空则保持不变。",
    },
    {
        "key": "WECHAT_MP_APP_SECRET",
        "label": "WeChat MP App Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "微信 H5 OAuth secret。只展示掩码，留空则保持不变。",
    },
    {
        "key": "MCP_BEARER_TOKEN",
        "label": "MCP Bearer Token",
        "mode": "masked",
        "input_type": "password",
        "description": "MCP 鉴权 token。只展示是否已配置，留空则保持不变。",
    },
)


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, field_name: str, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return number


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _filter_text_match(row: dict[str, Any], fields: list[str], query: str) -> bool:
    normalized_query = _normalized_text(query).lower()
    if not normalized_query:
        return True
    haystack = " ".join(_normalized_text(row.get(field)).lower() for field in fields)
    return normalized_query in haystack


def _setting_metadata_map() -> dict[str, dict[str, Any]]:
    return {item["key"]: dict(item) for item in APP_SETTING_DEFINITIONS}


def _operator(value: str | None) -> str:
    return _normalized_text(value) or "crm_console"


def _audit_log(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    repo.insert_admin_operation_log(
        operator=_operator(operator),
        action_type=action_type,
        target_type=target_type,
        target_id=_normalized_text(target_id),
        before_json=before or {},
        after_json=after or {},
    )


def _audit_meta_map(target_type: str, target_ids: list[str]) -> dict[str, dict[str, str]]:
    raw = repo.get_latest_audit_map(target_type=target_type, target_ids=target_ids)
    return {
        target_id: {
            "last_modified_at": _normalized_text(item.get("created_at")),
            "last_modified_by": _normalized_text(item.get("operator")),
            "last_action_type": _normalized_text(item.get("action_type")),
        }
        for target_id, item in raw.items()
    }


def _apply_audit_meta(rows: list[dict[str, Any]], *, target_type: str, id_field: str) -> list[dict[str, Any]]:
    audit_map = _audit_meta_map(target_type, [_normalized_text(row.get(id_field)) for row in rows])
    enriched: list[dict[str, Any]] = []
    for row in rows:
        row_id = _normalized_text(row.get(id_field))
        enriched.append({**row, **audit_map.get(row_id, {"last_modified_at": "", "last_modified_by": "", "last_action_type": ""})})
    return enriched


def _recent_audit_entries(target_type: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = repo.list_admin_operation_logs(target_type=target_type, limit=limit)
    return [
        {
            "operator": _normalized_text(row.get("operator")),
            "action_type": _normalized_text(row.get("action_type")),
            "target_id": _normalized_text(row.get("target_id")),
            "created_at": _normalized_text(row.get("created_at")),
        }
        for row in rows
    ]


def config_tabs(active_key: str) -> list[dict[str, Any]]:
    items = [
        {"key": "overview", "label": "概览", "href": "/admin/config"},
        {"key": "routing", "label": "Owner / Routing", "href": "/admin/config/routing"},
        {"key": "signup_tags", "label": "Signup Tags", "href": "/admin/config/signup-tags"},
        {"key": "class_term_tags", "label": "Class Term Tags", "href": "/admin/config/class-term-tags"},
        {"key": "app_settings", "label": "App Settings", "href": "/admin/config/app-settings"},
        {"key": "mcp_tools", "label": "MCP Tools", "href": "/admin/config/mcp-tools"},
    ]
    return [{**item, "active": item["key"] == active_key} for item in items]


def build_config_home_payload() -> dict[str, Any]:
    ensure_routing_rule_config_seed()
    ensure_class_term_tag_mapping_seed()
    routing_rows = list_routing_rules(active_only=False)
    signup_rules = tags_service.get_signup_tag_rules_config()
    class_term_rows = repo.list_class_term_tag_mappings(active_only=False)
    app_rows = list_admin_app_settings(query="", scope="")
    mcp_rows = list_mcp_tool_settings(query="", enabled_only=False)
    return {
        "cards": [
            {
                "label": "Owner / Routing",
                "value": len(routing_rows),
                "description": "owner_role_map + routing_rule_config",
                "href": "/admin/config/routing",
            },
            {
                "label": "Signup Tags",
                "value": len(signup_rules.get("items") or []),
                "description": f"missing {len(signup_rules.get('status_definitions') or []) - len(signup_rules.get('items') or [])}",
                "href": "/admin/config/signup-tags",
            },
            {
                "label": "Class Term Tags",
                "value": len(class_term_rows),
                "description": USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                "href": "/admin/config/class-term-tags",
            },
            {
                "label": "App Settings",
                "value": len(app_rows["rows"]),
                "description": "可编辑与掩码项分离",
                "href": "/admin/config/app-settings",
            },
            {
                "label": "MCP Tools",
                "value": len(mcp_rows["rows"]),
                "description": "tool enable/disable + console metadata",
                "href": "/admin/config/mcp-tools",
            },
        ]
    }


def list_owner_routing_settings(*, query: str, active_only: bool) -> dict[str, Any]:
    ensure_routing_rule_config_seed()
    owner_rows = [dict(item) for item in list_owner_role_map(active_only=active_only)]
    owner_rows = [row for row in owner_rows if _filter_text_match(row, ["userid", "display_name", "role"], query)]
    owner_rows = _apply_audit_meta(owner_rows, target_type=TARGET_OWNER_ROLE_MAP, id_field="userid")

    routing_rows = [dict(item) for item in list_routing_rules(active_only=active_only)]
    routing_rows = [
        row
        for row in routing_rows
        if _filter_text_match(
            row,
            [
                "rule_key",
                "routing_alias",
                "route_owner_userid",
                "route_owner_role",
                "routing_target",
                "fallback_target",
                "when_owner_role_sales",
                "when_owner_role_delivery",
            ],
            query,
        )
    ]
    routing_rows = _apply_audit_meta(routing_rows, target_type=TARGET_ROUTING_RULE_CONFIG, id_field="rule_key")

    return {
        "owner_rows": owner_rows,
        "routing_rows": routing_rows,
        "summary_cards": [
            {"label": "Owner Rows", "value": len(owner_rows), "description": "owner_role_map 当前条目"},
            {
                "label": "Active Owners",
                "value": sum(1 for row in owner_rows if bool(row.get("active"))),
                "description": "active = true",
            },
            {"label": "Routing Rules", "value": len(routing_rows), "description": "routing_rule_config 当前条目"},
            {
                "label": "Active Rules",
                "value": sum(1 for row in routing_rows if bool(row.get("active"))),
                "description": "active = true",
            },
        ],
        "audit_entries": _recent_audit_entries(TARGET_ROUTING_RULE_CONFIG, limit=8)
        + _recent_audit_entries(TARGET_OWNER_ROLE_MAP, limit=8),
        "role_options": list(OWNER_ROLE_OPTIONS),
        "routing_target_options": list(ROUTING_TARGET_OPTIONS),
    }


def save_owner_role_setting(payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
    userid = _normalized_text(payload.get("userid"))
    before = get_owner_role(userid)
    saved = save_owner_role_map_item(
        userid=userid,
        display_name=_normalized_text(payload.get("display_name")),
        role=_normalized_text(payload.get("role")),
        active=payload.get("active"),
    )
    _audit_log(
        operator=operator,
        action_type="update" if before else "create",
        target_type=TARGET_OWNER_ROLE_MAP,
        target_id=userid,
        before=before,
        after=saved,
    )
    return saved


def save_routing_rule_setting(payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
    rule_key = _normalized_text(payload.get("rule_key"))
    before = get_routing_rule(rule_key)
    saved = save_routing_rule_config_item(
        rule_key=rule_key,
        routing_alias=_normalized_text(payload.get("routing_alias")),
        route_owner_userid=_normalized_text(payload.get("route_owner_userid")),
        route_owner_role=_normalized_text(payload.get("route_owner_role")),
        routing_target=_normalized_text(payload.get("routing_target")),
        fallback_target=_normalized_text(payload.get("fallback_target")),
        when_owner_role_sales=_normalized_text(payload.get("when_owner_role_sales")),
        when_owner_role_delivery=_normalized_text(payload.get("when_owner_role_delivery")),
        active=payload.get("active"),
    )
    _audit_log(
        operator=operator,
        action_type="update" if before else "create",
        target_type=TARGET_ROUTING_RULE_CONFIG,
        target_id=saved.get("rule_key", rule_key),
        before=before,
        after=saved,
    )
    return saved


def list_signup_tag_settings(*, query: str, active_only: bool) -> dict[str, Any]:
    config = tags_service.get_signup_tag_rules_config()
    rows = [dict(item) for item in config.get("items") or []]
    if not active_only:
        rows = tags_service.repo.list_signup_tag_rules(active_only=False)  # type: ignore[attr-defined]
    rows = [dict(item) for item in rows if _filter_text_match(item, ["tag_id", "tag_name", "signup_status"], query)]
    rows = _apply_audit_meta(rows, target_type=TARGET_SIGNUP_TAG_RULE, id_field="tag_id")
    configured_statuses = {row["signup_status"] for row in rows if _normalized_text(row.get("signup_status"))}
    definitions = config.get("status_definitions") or []
    missing_statuses = [
        item["signup_status"]
        for item in definitions
        if item["signup_status"] not in configured_statuses
    ]
    return {
        "rows": rows,
        "definitions": definitions,
        "tag_group_name": config.get("tag_group_name", ""),
        "missing_statuses": missing_statuses,
        "bootstrap_initialized": not missing_statuses,
        "summary_cards": [
            {"label": "Definitions", "value": len(definitions), "description": "内部业务状态定义"},
            {"label": "Active Rules", "value": len(rows), "description": "signup_tag_rules 当前条目"},
            {"label": "Missing Statuses", "value": len(missing_statuses), "description": "未完成 bootstrap 的状态"},
        ],
        "audit_entries": _recent_audit_entries(TARGET_SIGNUP_TAG_RULE, limit=8),
    }


def save_signup_tag_setting(payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
    tag_id = _normalized_text(payload.get("tag_id"))
    before = next(
        (
            dict(item)
            for item in tags_service.repo.list_signup_tag_rules(active_only=False)  # type: ignore[attr-defined]
            if _normalized_text(item.get("tag_id")) == tag_id
        ),
        None,
    )
    saved = tags_service.save_signup_tag_rule_config(
        tag_id=tag_id,
        tag_name=_normalized_text(payload.get("tag_name")),
        signup_status=_normalized_text(payload.get("signup_status")),
        active=payload.get("active"),
    )
    _audit_log(
        operator=operator,
        action_type="update" if before else "create",
        target_type=TARGET_SIGNUP_TAG_RULE,
        target_id=tag_id,
        before=before,
        after=saved,
    )
    return saved


def _normalize_class_term_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "strategy_id": _normalized_text(row.get("strategy_id")),
        "group_id": _normalized_text(row.get("group_id")),
        "tag_id": _normalized_text(row.get("tag_id")),
        "tag_group_name": _normalized_text(row.get("tag_group_name")),
        "tag_name": _normalized_text(row.get("tag_name")),
        "class_term_no": int(row.get("class_term_no") or 0),
        "class_term_label": _normalized_text(row.get("class_term_label")),
        "is_active": bool(row.get("is_active")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def list_class_term_tag_mappings(*, query: str, active_only: bool) -> dict[str, Any]:
    ensure_class_term_tag_mapping_seed()
    rows = [_normalize_class_term_row(item) for item in repo.list_class_term_tag_mappings(active_only=active_only)]
    rows = [
        row
        for row in rows
        if _filter_text_match(
            row,
            ["class_term_label", "class_term_no", "tag_group_name", "tag_name", "tag_id", "group_id", "strategy_id"],
            query,
        )
    ]
    rows = _apply_audit_meta(rows, target_type=TARGET_CLASS_TERM_TAG_MAPPING, id_field="id")
    tag_id_configured = sum(1 for row in rows if row.get("tag_id"))
    return {
        "rows": rows,
        "summary_cards": [
            {"label": "Mappings", "value": len(rows), "description": "class_term_tag_mapping 当前条目"},
            {"label": "Active Rows", "value": sum(1 for row in rows if row["is_active"]), "description": "is_active = true"},
            {"label": "Tag IDs Ready", "value": tag_id_configured, "description": "已完成 WeCom tag 对齐"},
            {"label": "Missing Tag IDs", "value": max(len(rows) - tag_id_configured, 0), "description": "仍需补齐 tag_id / group_id"},
        ],
        "bootstrap_group_name": USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
        "audit_entries": _recent_audit_entries(TARGET_CLASS_TERM_TAG_MAPPING, limit=8),
    }


def save_class_term_tag_mapping(payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
    mapping_id_text = _normalized_text(payload.get("mapping_id"))
    mapping_id = int(mapping_id_text) if mapping_id_text else None
    class_term_no = _normalize_int(payload.get("class_term_no"), field_name="class_term_no", minimum=1)
    tag_group_name = _normalized_text(payload.get("tag_group_name")) or USER_OPS_CLASS_TERM_TAG_GROUP_NAME
    tag_name = _normalized_text(payload.get("tag_name"))
    class_term_label = _normalized_text(payload.get("class_term_label")) or f"{class_term_no}期"
    if not tag_name:
        raise ValueError("tag_name is required")
    before = repo.get_class_term_tag_mapping(mapping_id) if mapping_id else None
    saved_id = repo.upsert_class_term_tag_mapping(
        mapping_id=mapping_id,
        strategy_id=_normalized_text(payload.get("strategy_id")),
        group_id=_normalized_text(payload.get("group_id")),
        tag_id=_normalized_text(payload.get("tag_id")),
        tag_group_name=tag_group_name,
        tag_name=tag_name,
        class_term_no=class_term_no,
        class_term_label=class_term_label,
        is_active=_normalize_bool(payload.get("is_active")),
    )
    saved = repo.get_class_term_tag_mapping(saved_id) or {}
    _audit_log(
        operator=operator,
        action_type="update" if before else "create",
        target_type=TARGET_CLASS_TERM_TAG_MAPPING,
        target_id=str(saved_id),
        before=before,
        after=saved,
    )
    return _normalize_class_term_row(saved)


def _setting_value_source(key: str) -> tuple[str, str]:
    stored = get_setting(key)
    if stored is not None:
        return stored, "app_settings"
    return _normalized_text(current_app.config.get(key, "")), "config"


def _validate_known_setting(key: str, value: str) -> str:
    normalized = _normalized_text(value)
    if key == "WECOM_ARCHIVE_TIMEOUT":
        return str(_normalize_int(normalized or "0", field_name=key, minimum=1))
    if key == "WECOM_API_BASE" and normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError("WECOM_API_BASE must start with http:// or https://")
    return normalized


def list_admin_app_settings(*, query: str, scope: str) -> dict[str, Any]:
    metadata_map = _setting_metadata_map()
    audit_map = _audit_meta_map(TARGET_APP_SETTING, list(metadata_map.keys()))
    rows: list[dict[str, Any]] = []
    for item in APP_SETTING_DEFINITIONS:
        value, source = _setting_value_source(item["key"])
        display_value = mask_value(item["key"], value) if item["mode"] == "masked" else value
        row = {
            **item,
            "value": value if item["mode"] == "editable" else "",
            "display_value": display_value,
            "configured": bool(value),
            "source": source,
        }
        row.update(audit_map.get(item["key"], {"last_modified_at": "", "last_modified_by": "", "last_action_type": ""}))
        if scope and row["mode"] != scope:
            continue
        if not _filter_text_match(row, ["key", "label", "description"], query):
            continue
        rows.append(row)
    editable_count = sum(1 for row in rows if row["mode"] == "editable")
    masked_count = sum(1 for row in rows if row["mode"] == "masked")
    configured_count = sum(1 for row in rows if row["configured"])
    return {
        "rows": rows,
        "metadata_map": metadata_map,
        "summary_cards": [
            {"label": "Editable", "value": editable_count, "description": "可直接编辑项"},
            {"label": "Masked", "value": masked_count, "description": "secret / token 掩码项"},
            {"label": "Configured", "value": configured_count, "description": "当前已配置项"},
        ],
        "audit_entries": _recent_audit_entries(TARGET_APP_SETTING, limit=10),
    }


def save_admin_app_settings(payload: dict[str, Any], *, operator: str) -> list[dict[str, Any]]:
    metadata_map = _setting_metadata_map()
    changed_rows: list[dict[str, Any]] = []
    for key, raw_value in payload.items():
        normalized_key = _normalized_text(key)
        if not normalized_key:
            continue
        metadata = metadata_map.get(normalized_key)
        if metadata:
            if metadata["mode"] == "masked" and _normalized_text(raw_value) == "":
                continue
            validated = _validate_known_setting(normalized_key, _normalized_text(raw_value))
        else:
            validated = _normalized_text(raw_value)
        before_row = repo.get_app_setting_row(normalized_key)
        before_value = _normalized_text((before_row or {}).get("value"))
        if before_value == validated:
            continue
        repo.upsert_app_setting(key=normalized_key, value=validated)
        after_row = repo.get_app_setting_row(normalized_key) or {}
        _audit_log(
            operator=operator,
            action_type="update" if before_row else "create",
            target_type=TARGET_APP_SETTING,
            target_id=normalized_key,
            before=before_row,
            after=after_row,
        )
        changed_rows.append(after_row)
    return changed_rows


def list_settings_snapshot_compat() -> dict[str, str]:
    # Keep the historical /api/settings payload stable.
    from ...infra.settings import list_settings_snapshot

    return list_settings_snapshot(current_app.config)


def update_settings_compat(settings: dict[str, Any], *, operator: str) -> dict[str, str]:
    save_admin_app_settings(settings, operator=operator)
    return list_settings_snapshot_compat()


def _default_mcp_tool_defs() -> list[dict[str, Any]]:
    from ...mcp_adapter import TOOL_DEFS

    return [dict(item) for item in TOOL_DEFS]


def _default_tool_group(tool_name: str) -> str:
    if tool_name.startswith("create_") or tool_name.startswith("record_"):
        return "tasks"
    if "message_batch" in tool_name:
        return "ops"
    if tool_name in {"get_owner_role_map", "get_signup_tag_rules", "get_routing_config"}:
        return "config"
    if tool_name.startswith("get_") or tool_name.startswith("resolve_") or tool_name.startswith("search_"):
        return "crm"
    return "misc"


def _default_display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def ensure_mcp_tool_settings_seed() -> None:
    existing = {item["tool_name"]: item for item in repo.list_mcp_tool_settings()}
    for index, tool in enumerate(_default_mcp_tool_defs()):
        tool_name = _normalized_text(tool.get("name"))
        if not tool_name or tool_name in existing:
            continue
        repo.upsert_mcp_tool_setting(
            tool_name=tool_name,
            tool_group=_default_tool_group(tool_name),
            display_name=_default_display_name(tool_name),
            description_override="",
            enabled=True,
            visible_in_console=True,
            show_sample_args=False,
            show_sample_output=False,
            sort_order=index,
        )


def list_mcp_tool_settings(*, query: str, enabled_only: bool) -> dict[str, Any]:
    ensure_mcp_tool_settings_seed()
    defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _normalized_text(item.get("name"))}
    rows = []
    for item in repo.list_mcp_tool_settings():
        tool_name = _normalized_text(item.get("tool_name"))
        default = defaults.get(tool_name, {})
        row = {
            "tool_name": tool_name,
            "tool_group": _normalized_text(item.get("tool_group")) or _default_tool_group(tool_name),
            "display_name": _normalized_text(item.get("display_name")) or _default_display_name(tool_name),
            "description_override": _normalized_text(item.get("description_override")),
            "description": _normalized_text(item.get("description_override")) or _normalized_text(default.get("description")),
            "enabled": bool(item.get("enabled")),
            "visible_in_console": bool(item.get("visible_in_console")),
            "show_sample_args": bool(item.get("show_sample_args")),
            "show_sample_output": bool(item.get("show_sample_output")),
            "sort_order": int(item.get("sort_order") or 0),
            "updated_at": _normalized_text(item.get("updated_at")),
        }
        if enabled_only and not row["enabled"]:
            continue
        if not _filter_text_match(row, ["tool_name", "tool_group", "display_name", "description"], query):
            continue
        rows.append(row)
    rows = _apply_audit_meta(rows, target_type=TARGET_MCP_TOOL_SETTING, id_field="tool_name")
    auth_value, auth_source = _setting_value_source("MCP_BEARER_TOKEN")
    return {
        "rows": rows,
        "auth_configured": bool(auth_value),
        "auth_source": auth_source,
        "summary_cards": [
            {"label": "Tools", "value": len(rows), "description": "已表化 MCP tool settings"},
            {"label": "Enabled", "value": sum(1 for row in rows if row["enabled"]), "description": "运行时启用工具"},
            {"label": "Visible", "value": sum(1 for row in rows if row["visible_in_console"]), "description": "后台展示工具"},
            {"label": "Auth", "value": "configured" if auth_value else "missing", "description": "MCP auth token 状态"},
        ],
        "audit_entries": _recent_audit_entries(TARGET_MCP_TOOL_SETTING, limit=8),
    }


def save_mcp_tool_setting(payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
    tool_name = _normalized_text(payload.get("tool_name"))
    defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _normalized_text(item.get("name"))}
    if tool_name not in defaults:
        raise ValueError("tool_name is invalid")
    before = repo.get_mcp_tool_setting(tool_name)
    repo.upsert_mcp_tool_setting(
        tool_name=tool_name,
        tool_group=_normalized_text(payload.get("tool_group")) or _default_tool_group(tool_name),
        display_name=_normalized_text(payload.get("display_name")) or _default_display_name(tool_name),
        description_override=_normalized_text(payload.get("description_override")),
        enabled=_normalize_bool(payload.get("enabled")),
        visible_in_console=_normalize_bool(payload.get("visible_in_console")),
        show_sample_args=_normalize_bool(payload.get("show_sample_args")),
        show_sample_output=_normalize_bool(payload.get("show_sample_output")),
        sort_order=_normalize_int(payload.get("sort_order") or 0, field_name="sort_order", minimum=0),
    )
    saved = repo.get_mcp_tool_setting(tool_name) or {}
    _audit_log(
        operator=operator,
        action_type="update" if before else "create",
        target_type=TARGET_MCP_TOOL_SETTING,
        target_id=tool_name,
        before=before,
        after=saved,
    )
    return dict(saved)


def list_mcp_runtime_tools() -> list[dict[str, Any]]:
    payload = list_mcp_tool_settings(query="", enabled_only=True)
    defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _normalized_text(item.get("name"))}
    result: list[dict[str, Any]] = []
    for row in sorted(payload["rows"], key=lambda item: (int(item.get("sort_order") or 0), item["tool_name"])):
        default = defaults.get(row["tool_name"], {})
        result.append(
            {
                **default,
                "name": row["tool_name"],
                "description": row["description"],
            }
        )
    return result


def mcp_tool_enabled(tool_name: str) -> bool:
    payload = list_mcp_tool_settings(query="", enabled_only=False)
    matched = next((item for item in payload["rows"] if item["tool_name"] == _normalized_text(tool_name)), None)
    return bool((matched or {}).get("enabled"))
