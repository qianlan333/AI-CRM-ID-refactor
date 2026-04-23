from __future__ import annotations

from typing import Any, Iterable

from flask import current_app

from ..admin_config import repo as admin_config_repo
from ...infra.settings import get_setting
from . import repo

ROLE_LABELS = {
    "super_admin": "超级管理员",
    "automation_admin": "自动化管理员",
    "questionnaire_admin": "问卷管理员",
    "config_admin": "配置管理员",
    "viewer": "只读查看者",
}

MODULE_LABELS = {
    "automation_conversion": "自动化运营",
    "questionnaires": "问卷",
    "config": "配置",
    "api_docs": "API 文档",
    "sunset": "已下线模块",
}

ROLE_MODULE_ACCESS = {
    "super_admin": {"automation_conversion", "questionnaires", "config", "api_docs", "sunset"},
    "automation_admin": {"automation_conversion", "api_docs", "sunset"},
    "questionnaire_admin": {"questionnaires", "api_docs", "sunset"},
    "config_admin": {"config", "api_docs", "sunset"},
    "viewer": {"automation_conversion", "questionnaires", "config", "api_docs", "sunset"},
}

READ_ONLY_ROLES = {"viewer"}

ADMIN_ROLE_OPTIONS = [{"value": code, "label": label} for code, label in ROLE_LABELS.items()]


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalized_role_codes(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        candidates = list(value)
    elif value is None:
        candidates = []
    else:
        candidates = [item.strip() for item in str(value).split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        role_code = _normalized_text(candidate)
        if not role_code or role_code in seen:
            continue
        if role_code not in ROLE_LABELS:
            raise ValueError("角色不合法")
        deduped.append(role_code)
        seen.add(role_code)
    if not deduped:
        raise ValueError("至少选择一个角色")
    return deduped


def _validate_wecom_userid(value: Any) -> str:
    wecom_userid = _normalized_text(value)
    if not wecom_userid:
        raise ValueError("企微成员 UserId 不能为空")
    if len(wecom_userid) > 128:
        raise ValueError("企微成员 UserId 过长")
    return wecom_userid


def _role_labels(role_codes: Iterable[str]) -> list[str]:
    return [ROLE_LABELS.get(role_code, role_code) for role_code in role_codes]


def _setting_or_config(key: str, config: dict[str, Any] | None = None) -> str:
    if config is None:
        config = dict(current_app.config)
    return _normalized_text(get_setting(key)) or _normalized_text(config.get(key, ""))


def is_break_glass_login_enabled() -> bool:
    value = _setting_or_config("ADMIN_BREAK_GLASS_LOGIN_ENABLED")
    return value.lower() in {"1", "true", "yes", "on"}


def _present_admin_users(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_rows = repo.list_admin_user_roles([int(row.get("id") or 0) for row in rows if int(row.get("id") or 0) > 0])
    role_map: dict[int, list[str]] = {}
    for role_row in role_rows:
        user_id = int(role_row.get("admin_user_id") or 0)
        if user_id <= 0:
            continue
        role_map.setdefault(user_id, []).append(_normalized_text(role_row.get("role_code")))
    presented: list[dict[str, Any]] = []
    for row in rows:
        user_id = int(row.get("id") or 0)
        role_codes = [role_code for role_code in role_map.get(user_id, []) if role_code]
        presented.append(
            {
                "id": user_id,
                "wecom_userid": _normalized_text(row.get("wecom_userid")),
                "wecom_corpid": _normalized_text(row.get("wecom_corpid")),
                "display_name": _normalized_text(row.get("display_name")) or _normalized_text(row.get("wecom_userid")),
                "roles": role_codes,
                "role_labels": _role_labels(role_codes),
                "roles_display": " / ".join(_role_labels(role_codes)) or "-",
                "is_active": bool(row.get("is_active")),
                "auth_source": _normalized_text(row.get("auth_source")) or "wecom_sso",
                "last_login_at": _normalized_text(row.get("last_login_at")),
                "created_at": _normalized_text(row.get("created_at")),
                "updated_at": _normalized_text(row.get("updated_at")),
            }
        )
    return presented


def count_admin_users() -> int:
    return repo.count_admin_users()


def get_admin_user_by_id(user_id: int | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    row = repo.get_admin_user_by_id(int(user_id))
    rows = _present_admin_users([row] if row else [])
    return rows[0] if rows else None


def get_admin_user_by_wecom_userid(wecom_userid: str, *, wecom_corpid: str = "") -> dict[str, Any] | None:
    row = repo.get_admin_user_by_wecom_userid(wecom_userid, wecom_corpid=wecom_corpid)
    rows = _present_admin_users([row] if row else [])
    return rows[0] if rows else None


def touch_admin_user_login(user_id: int) -> None:
    repo.update_admin_user_last_login(int(user_id))


def record_admin_login(
    *,
    admin_user_id: int | None,
    login_type: str,
    login_result: str,
    ip: str,
    user_agent: str,
) -> None:
    repo.insert_admin_login_audit(
        admin_user_id=admin_user_id,
        login_type=login_type,
        login_result=login_result,
        ip=ip,
        user_agent=user_agent,
    )


def admin_role_can_access_module(role_codes: str | Iterable[str], module_key: str, *, write: bool = False) -> bool:
    if isinstance(role_codes, str):
        normalized_roles = [_normalized_text(role_codes)]
    else:
        normalized_roles = [_normalized_text(role_code) for role_code in role_codes]
    effective_roles = [role_code for role_code in normalized_roles if role_code]
    if "super_admin" in effective_roles:
        return True
    normalized_module = _normalized_text(module_key) or "sunset"
    if write:
        return any(
            normalized_module in ROLE_MODULE_ACCESS.get(role_code, set()) and role_code not in READ_ONLY_ROLES
            for role_code in effective_roles
        )
    return any(normalized_module in ROLE_MODULE_ACCESS.get(role_code, set()) for role_code in effective_roles)


def build_admin_account_page_payload() -> dict[str, Any]:
    rows = _present_admin_users(repo.list_admin_users())
    login_audit_rows = repo.list_admin_login_audit(limit=20)
    return {
        "rows": rows,
        "role_options": list(ADMIN_ROLE_OPTIONS),
        "role_labels": dict(ROLE_LABELS),
        "break_glass_enabled": is_break_glass_login_enabled(),
        "auth_mode": _setting_or_config("ADMIN_AUTH_MODE") or "wecom_sso",
        "corp_id": _setting_or_config("WECOM_CORP_ID"),
        "login_audit_rows": [
            {
                "id": int(row.get("id") or 0),
                "admin_user_id": int(row.get("admin_user_id") or 0) if row.get("admin_user_id") else None,
                "wecom_userid": _normalized_text(row.get("wecom_userid")),
                "display_name": _normalized_text(row.get("display_name")),
                "login_type": _normalized_text(row.get("login_type")),
                "login_result": _normalized_text(row.get("login_result")),
                "ip": _normalized_text(row.get("ip")),
                "user_agent": _normalized_text(row.get("user_agent")),
                "created_at": _normalized_text(row.get("created_at")),
            }
            for row in login_audit_rows
        ],
    }


def save_admin_user(payload: dict[str, Any], *, operator: str = "crm_console") -> dict[str, Any]:
    user_id = int(payload.get("id") or 0) or None
    wecom_userid = _validate_wecom_userid(payload.get("wecom_userid"))
    display_name = _normalized_text(payload.get("display_name")) or wecom_userid
    wecom_corpid = _normalized_text(payload.get("wecom_corpid")) or _setting_or_config("WECOM_CORP_ID")
    is_active = _normalized_bool(payload.get("is_active"), default=True)
    auth_source = _normalized_text(payload.get("auth_source")) or "wecom_sso"
    role_codes = _normalized_role_codes(payload.get("role_codes") or payload.get("role_code"))

    existing_by_userid = repo.get_admin_user_by_wecom_userid(wecom_userid, wecom_corpid=wecom_corpid)
    if existing_by_userid and int(existing_by_userid.get("id") or 0) != int(user_id or 0):
        raise ValueError("该企微成员已经授权")

    if user_id:
        existing = get_admin_user_by_id(int(user_id))
        if not existing:
            raise ValueError("授权成员不存在")
        repo.update_admin_user(
            user_id=int(user_id),
            wecom_userid=wecom_userid,
            wecom_corpid=wecom_corpid,
            display_name=display_name,
            is_active=is_active,
            auth_source=auth_source,
        )
        repo.replace_admin_user_roles(admin_user_id=int(user_id), role_codes=role_codes)
        saved = get_admin_user_by_id(int(user_id))
        admin_config_repo.insert_admin_operation_log(
            operator=_normalized_text(operator) or "crm_console",
            action_type="update_admin_user",
            target_type="admin_user",
            target_id=wecom_userid,
            before_json={"user": existing or {}},
            after_json={"user": saved or {}},
        )
        if not saved:
            raise ValueError("保存授权成员失败")
        return saved

    created_id = repo.insert_admin_user(
        wecom_userid=wecom_userid,
        wecom_corpid=wecom_corpid,
        display_name=display_name,
        is_active=is_active,
        auth_source=auth_source,
    )
    repo.replace_admin_user_roles(admin_user_id=created_id, role_codes=role_codes)
    saved = get_admin_user_by_id(created_id)
    admin_config_repo.insert_admin_operation_log(
        operator=_normalized_text(operator) or "crm_console",
        action_type="create_admin_user",
        target_type="admin_user",
        target_id=wecom_userid,
        before_json={},
        after_json={"user": saved or {}},
    )
    if not saved:
        raise ValueError("创建授权成员失败")
    return saved
