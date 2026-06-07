from __future__ import annotations

import json
import os
from typing import Any

from aicrm_next.admin_jobs.routes import ensure_admin_action_token

from .definitions import APP_SETTING_DEFINITIONS
from .repository import AdminConfigRepository
from .schema import CONFIG_SCHEMA, build_config_checklist, validate_config
from .settings import SENSITIVE_KEYS, mask_value


TARGET_APP_SETTING = "app_setting"
TARGET_ADMIN_USER = "admin_user"
TARGET_MCP_TOOL_SETTING = "mcp_tool_setting"

ROLE_LABELS = {
    "super_admin": "超级管理员",
    "config_admin": "配置管理员",
    "automation_admin": "自动化管理员",
    "questionnaire_admin": "问卷管理员",
    "viewer": "只读成员",
}
ADMIN_ASSIGNABLE_ROLE_OPTIONS = [{"value": key, "label": value} for key, value in ROLE_LABELS.items() if key != "super_admin"]
ADMIN_LEVEL_LABELS = {"super_admin": "超级管理员", "admin": "管理员"}
MCP_TOOL_GROUP_LABELS = {
    "crm": "客户查询",
    "tasks": "触达任务",
    "config": "配置规则",
    "ops": "同步任务",
    "misc": "其他",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _filter_text_match(row: dict[str, Any], fields: list[str], query: str) -> bool:
    normalized = _text(query).lower()
    if not normalized:
        return True
    haystack = " ".join(_text(row.get(field)).lower() for field in fields)
    return normalized in haystack


def _normalize_int(value: Any, *, field_name: str, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} 不能小于 {minimum}")
    return number


def _validate_known_setting(key: str, value: str) -> str:
    normalized = _text(value)
    if key in {
        "WECOM_CORP_TAG_LIMIT",
        "WECOM_ARCHIVE_TIMEOUT",
        "DEEPSEEK_TIMEOUT_SECONDS",
        "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "LAOHUANG_CHAT_TIMEOUT_SECONDS",
        "WECHAT_PAY_TIMEOUT_SECONDS",
        "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS",
        "OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS",
    }:
        return str(_normalize_int(normalized or "0", field_name=key, minimum=1))
    if key in {
        "OUTBOUND_WEBHOOK_RETRY_ENABLED",
        "DEEPSEEK_ENABLED",
        "LAOHUANG_CHAT_ENABLED",
        "WECHAT_PAY_ENABLED",
        "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED",
        "ADMIN_BREAK_GLASS_LOGIN_ENABLED",
    }:
        return "true" if normalized.lower() in {"1", "true", "yes", "y", "on"} else "false"
    if key == "LAOHUANG_CHAT_SEND_CHANNEL":
        if normalized and normalized != "private_message":
            raise ValueError("LAOHUANG_CHAT_SEND_CHANNEL 首版只允许 private_message")
        return normalized or "private_message"
    if key in {
        "WECOM_API_BASE",
        "DEEPSEEK_BASE_URL",
        "OPENCLAW_WEBHOOK_URL",
        "LAOHUANG_CHAT_WEBHOOK_URL",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
        "WECHAT_PAY_NOTIFY_URL",
        "WECHAT_PAY_API_BASE",
    } and normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{key} 必须以 http:// 或 https:// 开头")
    if key == "WECHAT_PAY_PRODUCT_CATALOG_JSON" and normalized:
        try:
            json.loads(normalized)
        except ValueError as exc:
            raise ValueError("WECHAT_PAY_PRODUCT_CATALOG_JSON 必须是合法 JSON") from exc
    return normalized


def _default_mcp_tool_defs() -> list[dict[str, Any]]:
    from aicrm_next.integration_gateway.mcp import MCP_TOOLS

    return [dict(item) for item in MCP_TOOLS]


def _default_tool_group(tool_name: str) -> str:
    if tool_name.startswith(("create_", "record_", "send_")):
        return "tasks"
    if "message_batch" in tool_name:
        return "ops"
    if tool_name.startswith(("get_", "resolve_", "search_")):
        return "crm"
    return "misc"


def _default_display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def _tool_group_label(value: str) -> str:
    normalized = _text(value)
    return MCP_TOOL_GROUP_LABELS.get(normalized, normalized or "-")


def _default_tool_description(tool_name: str, fallback: str = "") -> str:
    mapping = {
        "resolve_customer": "根据手机号、客户编号或 external_userid 定位客户。",
        "get_customer_context": "查看客户资料、互动记录和最近聊天。",
        "get_recent_messages": "查看客户最近聊天。",
        "get_automation_context": "查看自动化成员上下文。",
    }
    return mapping.get(tool_name, fallback)


def _audit_action_label(action_type: str) -> str:
    mapping = {"create": "新建", "update": "更新"}
    normalized = _text(action_type)
    return mapping.get(normalized, normalized or "-")


class AdminConfigReadService:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def config_tabs(self, active_key: str) -> list[dict[str, Any]]:
        items = [
            {"key": "overview", "label": "概览", "href": "/admin/config"},
            {"key": "app_settings", "label": "系统设置", "href": "/admin/config/app-settings"},
            {"key": "login_access", "label": "登录与权限", "href": "/admin/config/login-access"},
            {"key": "checklist", "label": "配置检查清单", "href": "/admin/config/checklist"},
        ]
        return [{**item, "active": item["key"] == active_key} for item in items]

    def _setting_value_source(self, key: str) -> tuple[str, str]:
        row = self.repo.get_app_setting(key)
        if row is not None:
            return _text(row.get("value")), "app_settings"
        env_value = _text(os.getenv(key))
        return env_value, "config"

    def _current_setting_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for group in CONFIG_SCHEMA.values():
            for field_key in group["fields"]:
                value, _source = self._setting_value_source(field_key)
                if value:
                    values[field_key] = value
        return values

    def _audit_meta_map(self, target_ids: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for target_id, row in self.repo.latest_audit_map(target_type=TARGET_APP_SETTING, target_ids=target_ids).items():
            result[target_id] = {
                "last_modified_at": _text(row.get("created_at")),
                "last_modified_by": _text(row.get("operator")),
                "last_action_type": _text(row.get("action_type")),
            }
        return result

    def _recent_audit_entries(self, target_type: str, limit: int = 8) -> list[dict[str, str]]:
        return [
            {
                "id": _text(row.get("id")),
                "operator": _text(row.get("operator")),
                "action_type": _text(row.get("action_type")),
                "target_id": _text(row.get("target_id")),
                "created_at": _text(row.get("created_at")),
            }
            for row in self.repo.list_audit_logs(target_type=target_type, limit=limit)
        ]

    def ensure_mcp_tool_settings_seed(self) -> None:
        existing = {item["tool_name"]: item for item in self.repo.list_mcp_tool_settings()}
        for index, tool in enumerate(_default_mcp_tool_defs()):
            tool_name = _text(tool.get("name"))
            if not tool_name or tool_name in existing:
                continue
            self.repo.upsert_mcp_tool_setting(
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

    def build_home_payload(self) -> dict[str, Any]:
        app_rows = self.list_app_settings(query="", scope="")
        return {
            "cards": [
                {
                    "label": "系统设置",
                    "value": len(app_rows["rows"]),
                    "description": "维护渠道、Webhook 与其他系统级参数",
                    "href": "/admin/config/app-settings",
                },
                {
                    "label": "登录与权限",
                    "value": self.repo.count_admin_users(),
                    "description": "维护企微成员授权、角色分配、启停状态与登录审计",
                    "href": "/admin/config/login-access",
                },
            ]
        }

    def list_app_settings(self, *, query: str, scope: str) -> dict[str, Any]:
        definitions = [dict(item) for item in APP_SETTING_DEFINITIONS]
        metadata = {item["key"]: dict(item) for item in definitions}
        audit_map = self._audit_meta_map(list(metadata.keys()))
        rows: list[dict[str, Any]] = []
        for item in definitions:
            value, source = self._setting_value_source(item["key"])
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
            "metadata_map": metadata,
            "summary_cards": [
                {"label": "可直接编辑", "value": editable_count, "description": "可以直接修改的设置项"},
                {"label": "敏感信息", "value": masked_count, "description": "只显示掩码的设置项"},
                {"label": "已配置", "value": configured_count, "description": "当前已经配置完成的设置项"},
            ],
            "audit_entries": self._recent_audit_entries(TARGET_APP_SETTING, limit=10),
        }

    def list_mcp_tool_settings(self, *, query: str, enabled_only: bool) -> dict[str, Any]:
        self.ensure_mcp_tool_settings_seed()
        defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _text(item.get("name"))}
        audit_map = self._audit_meta_map_for_type(
            TARGET_MCP_TOOL_SETTING,
            [item["tool_name"] for item in self.repo.list_mcp_tool_settings()],
        )
        rows: list[dict[str, Any]] = []
        for item in self.repo.list_mcp_tool_settings():
            tool_name = _text(item.get("tool_name"))
            default = defaults.get(tool_name, {})
            tool_group = _text(item.get("tool_group")) or _default_tool_group(tool_name)
            raw_display_name = _text(item.get("display_name"))
            description_override = _text(item.get("description_override"))
            row = {
                "tool_name": tool_name,
                "tool_group": tool_group,
                "tool_group_label": _tool_group_label(tool_group),
                "display_name": raw_display_name or _default_display_name(tool_name),
                "description_override": description_override,
                "description": description_override or _default_tool_description(tool_name, _text(default.get("description"))),
                "enabled": _bool(item.get("enabled")),
                "visible_in_console": _bool(item.get("visible_in_console")),
                "show_sample_args": _bool(item.get("show_sample_args")),
                "show_sample_output": _bool(item.get("show_sample_output")),
                "sort_order": int(item.get("sort_order") or 0),
                "updated_at": _text(item.get("updated_at")),
            }
            row.update(audit_map.get(tool_name, {"last_modified_at": "", "last_modified_by": "", "last_action_type": ""}))
            if enabled_only and not row["enabled"]:
                continue
            if not _filter_text_match(row, ["tool_name", "tool_group", "display_name", "description"], query):
                continue
            rows.append(row)
        auth_value, auth_source = self._setting_value_source("MCP_BEARER_TOKEN")
        return {
            "rows": rows,
            "auth_configured": bool(auth_value),
            "auth_source": auth_source,
            "summary_cards": [
                {"label": "工具数量", "value": len(rows), "description": "当前可管理的 AI 工具数量"},
                {"label": "已启用", "value": sum(1 for row in rows if row["enabled"]), "description": "当前允许调用的工具数量"},
                {"label": "后台展示", "value": sum(1 for row in rows if row["visible_in_console"]), "description": "当前在后台显示的工具数量"},
                {"label": "访问令牌", "value": "已配置" if auth_value else "未配置", "description": "AI 工具访问令牌状态"},
            ],
            "audit_entries": [
                {**item, "action_label": _audit_action_label(item["action_type"])}
                for item in self._recent_audit_entries(TARGET_MCP_TOOL_SETTING, limit=8)
            ],
        }

    def _audit_meta_map_for_type(self, target_type: str, target_ids: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for target_id, row in self.repo.latest_audit_map(target_type=target_type, target_ids=target_ids).items():
            result[target_id] = {
                "last_modified_at": _text(row.get("created_at")),
                "last_modified_by": _text(row.get("operator")),
                "last_action_type": _text(row.get("action_type")),
            }
        return result

    def schema_groups(self) -> list[dict[str, Any]]:
        return [
            {"label": group["label"], "required": group.get("required", False), "fields": group["fields"]}
            for group in CONFIG_SCHEMA.values()
        ]

    def masked_setting_values(self) -> dict[str, str]:
        return {key: mask_value(key, value) for key, value in self._current_setting_values().items()}

    def build_checklist(self) -> list[dict[str, Any]]:
        return build_config_checklist(self._current_setting_values())

    def build_login_access_payload(self) -> dict[str, Any]:
        rows = self._admin_user_rows()
        login_audit_rows = [
            {
                "created_at": _text(row.get("created_at")),
                "display_name": _text(row.get("display_name")),
                "wecom_userid": _text(row.get("wecom_userid")),
                "login_type": _text(row.get("login_type")),
                "login_result": _text(row.get("login_result")),
                "ip": _text(row.get("ip")),
                "user_agent": _text(row.get("user_agent")),
            }
            for row in self.repo.list_admin_login_audit(limit=20)
        ]
        corp_id = self._setting_value_source("WECOM_CORP_ID")[0]
        directory_members = self._directory_members_from_admin_users(rows, corp_id=corp_id)
        return {
            "rows": rows,
            "super_admin_rows": [row for row in rows if row.get("admin_level") == "super_admin"],
            "admin_rows": [row for row in rows if row.get("admin_level") != "super_admin"],
            "directory_members": directory_members,
            "directory_summary": {
                "count": len(directory_members),
                "authorized_count": sum(1 for row in directory_members if row.get("is_authorized")),
                "last_synced_at": "",
            },
            "role_options": [{"value": key, "label": value} for key, value in ROLE_LABELS.items()],
            "assignable_role_options": list(ADMIN_ASSIGNABLE_ROLE_OPTIONS),
            "role_labels": dict(ROLE_LABELS),
            "admin_level_labels": dict(ADMIN_LEVEL_LABELS),
            "login_audit_rows": login_audit_rows,
            "break_glass_enabled": self._setting_value_source("ADMIN_BREAK_GLASS_LOGIN_ENABLED")[0].lower() in {"1", "true", "yes", "on"},
            "auth_mode": self._setting_value_source("ADMIN_AUTH_MODE")[0] or "wecom_sso",
            "corp_id": corp_id,
        }

    def _admin_user_rows(self) -> list[dict[str, Any]]:
        raw_rows = self.repo.list_admin_users()
        role_rows = self.repo.list_admin_user_roles([int(row.get("id") or 0) for row in raw_rows])
        role_map: dict[int, list[str]] = {}
        for row in role_rows:
            role_map.setdefault(int(row.get("admin_user_id") or 0), []).append(_text(row.get("role_code")))
        rows: list[dict[str, Any]] = []
        for row in raw_rows:
            user_id = int(row.get("id") or 0)
            roles = [role for role in role_map.get(user_id, []) if role]
            admin_level = _text(row.get("admin_level")) or ("super_admin" if "super_admin" in roles else "admin")
            rows.append(
                {
                    **row,
                    "id": user_id,
                    "roles": roles,
                    "role_labels": [ROLE_LABELS.get(role, role) for role in roles],
                    "roles_display": " / ".join(ROLE_LABELS.get(role, role) for role in roles) or "-",
                    "is_active": _bool(row.get("is_active")),
                    "login_enabled": _bool(row.get("login_enabled")),
                    "admin_level": admin_level,
                    "admin_level_label": ADMIN_LEVEL_LABELS.get(admin_level, admin_level),
                }
            )
        return rows

    def _directory_members_from_admin_users(self, rows: list[dict[str, Any]], *, corp_id: str) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            result.append(
                {
                    "wecom_userid": _text(row.get("wecom_userid")),
                    "display_name": _text(row.get("display_name")) or _text(row.get("wecom_userid")),
                    "wecom_corpid": _text(row.get("wecom_corpid")) or corp_id,
                    "department_ids_display": "",
                    "position": "",
                    "status_label": "已授权",
                    "is_authorized": True,
                    "admin_user_id": row.get("id"),
                    "admin_login_enabled": row.get("login_enabled"),
                    "admin_level": row.get("admin_level"),
                    "admin_level_label": row.get("admin_level_label"),
                }
            )
        return result


class AdminConfigWriteCommand:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def execute(self, settings: dict[str, Any], *, operator: str) -> list[dict[str, Any]]:
        metadata = {item["key"]: dict(item) for item in APP_SETTING_DEFINITIONS}
        changed: list[dict[str, Any]] = []
        for key, raw_value in settings.items():
            normalized_key = _text(key)
            if not normalized_key:
                continue
            metadata_row = metadata.get(normalized_key)
            if metadata_row:
                if metadata_row["mode"] == "masked" and _text(raw_value) == "":
                    continue
                validated = _validate_known_setting(normalized_key, _text(raw_value))
            else:
                validated = _text(raw_value)
            before = self.repo.get_app_setting(normalized_key)
            if _text((before or {}).get("value")) == validated:
                continue
            after = self.repo.upsert_app_setting(key=normalized_key, value=validated)
            self.repo.insert_audit_log(
                operator=operator,
                action_type="update" if before else "create",
                target_type=TARGET_APP_SETTING,
                target_id=normalized_key,
                before=before or {},
                after=after,
            )
            changed.append(after)
        return changed


class SetupWizardStateService:
    def __init__(self, read_service: AdminConfigReadService | None = None) -> None:
        self.read_service = read_service or AdminConfigReadService()

    def build_state(self, *, validation_errors: list[dict[str, str]] | None = None, save_success: bool = False) -> dict[str, Any]:
        return {
            "schema_groups": self.read_service.schema_groups(),
            "current_values": self.read_service.masked_setting_values(),
            "validation_errors": validation_errors or [],
            "save_success": save_success,
            "admin_action_token": ensure_admin_action_token(),
        }


class SetupWizardSaveCommand:
    def __init__(
        self,
        read_service: AdminConfigReadService | None = None,
        write_command: AdminConfigWriteCommand | None = None,
    ) -> None:
        self.read_service = read_service or AdminConfigReadService()
        self.write_command = write_command or AdminConfigWriteCommand()

    def execute(self, form_payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        settings_to_save: dict[str, str] = {}
        for raw_key, raw_value in form_payload.items():
            key = _text(raw_key)
            if not key.startswith("setting__"):
                continue
            field_key = key[len("setting__") :]
            value = _text(raw_value)
            if field_key in SENSITIVE_KEYS and not value:
                continue
            settings_to_save[field_key] = value
        merged = self.read_service._current_setting_values()
        merged.update(settings_to_save)
        errors = validate_config(merged)
        if errors:
            return {"ok": False, "validation_errors": errors, "changed": []}
        changed = self.write_command.execute(settings_to_save, operator=operator) if settings_to_save else []
        return {
            "ok": True,
            "validation_errors": [],
            "changed": changed,
            "source_status": "next_command",
            "fallback_used": False,
            "real_external_call_executed": False,
        }


class LoginAccessSaveCommand:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def execute(self, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        wecom_userid = _text(payload.get("wecom_userid"))
        if not wecom_userid:
            raise ValueError("wecom_userid is required")
        admin_level = _text(payload.get("admin_level")) or "admin"
        if admin_level not in {"admin", "super_admin"}:
            raise ValueError("admin_level must be admin or super_admin")
        raw_roles = payload.get("role_codes") or []
        if isinstance(raw_roles, str):
            raw_roles = [raw_roles]
        roles = [_text(role) for role in raw_roles if _text(role) in ROLE_LABELS and _text(role) != "super_admin"]
        if admin_level == "super_admin":
            roles = ["super_admin"]
        elif not roles:
            roles = ["viewer"]
        before = self.repo.get_admin_user(int(payload.get("id") or 0)) if _text(payload.get("id")) else self.repo.get_admin_user_by_wecom_userid(wecom_userid)
        user_payload = {
            "id": int(payload.get("id") or 0),
            "wecom_userid": wecom_userid,
            "wecom_corpid": _text(payload.get("wecom_corpid")),
            "display_name": _text(payload.get("display_name")) or wecom_userid,
            "is_active": _bool(payload.get("is_active", True)),
            "auth_source": _text(payload.get("auth_source")) or "wecom_sso",
            "updated_by": operator,
            "login_enabled": _bool(payload.get("login_enabled", True)),
            "admin_level": admin_level,
        }
        saved = self.repo.upsert_admin_user(user_payload)
        self.repo.replace_admin_user_roles(admin_user_id=int(saved.get("id") or 0), role_codes=roles)
        after = self.repo.get_admin_user(int(saved.get("id") or 0)) or saved
        self.repo.insert_audit_log(
            operator=operator,
            action_type="update" if before else "create",
            target_type=TARGET_ADMIN_USER,
            target_id=_text(after.get("id")),
            before=before or {},
            after={**after, "roles": roles},
        )
        return {**after, "roles": roles}


class McpToolSettingSaveCommand:
    def __init__(self, repo: AdminConfigRepository | None = None, read_service: AdminConfigReadService | None = None) -> None:
        self.repo = repo or AdminConfigRepository()
        self.read_service = read_service or AdminConfigReadService(self.repo)

    def execute(self, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        self.read_service.ensure_mcp_tool_settings_seed()
        tool_name = _text(payload.get("tool_name") or payload.get("tool_key"))
        defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _text(item.get("name"))}
        if tool_name not in defaults:
            raise ValueError("工具名称不合法")
        before = self.repo.get_mcp_tool_setting(tool_name)
        saved = self.repo.upsert_mcp_tool_setting(
            tool_name=tool_name,
            tool_group=_text(payload.get("tool_group")) or _default_tool_group(tool_name),
            display_name=_text(payload.get("display_name")) or _default_display_name(tool_name),
            description_override=_text(payload.get("description_override")),
            enabled=_bool(payload.get("enabled")),
            visible_in_console=_bool(payload.get("visible_in_console", True)),
            show_sample_args=_bool(payload.get("show_sample_args")),
            show_sample_output=_bool(payload.get("show_sample_output")),
            sort_order=_normalize_int(payload.get("sort_order") or 0, field_name="sort_order", minimum=0),
        )
        self.repo.insert_audit_log(
            operator=operator,
            action_type="update" if before else "create",
            target_type=TARGET_MCP_TOOL_SETTING,
            target_id=tool_name,
            before=before or {},
            after=saved,
        )
        return {
            **saved,
            "enabled": _bool(saved.get("enabled")),
            "visible_in_console": _bool(saved.get("visible_in_console")),
            "show_sample_args": _bool(saved.get("show_sample_args")),
            "show_sample_output": _bool(saved.get("show_sample_output")),
        }
