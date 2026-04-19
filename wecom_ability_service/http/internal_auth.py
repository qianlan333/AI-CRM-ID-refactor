from __future__ import annotations

import secrets

from flask import current_app, jsonify, request, session

from ..infra.internal_auth_runtime import require_internal_api_token_compat

ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY = "admin_console_action_token"


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def require_internal_api_token(
    *,
    token_keys: tuple[str, ...] = (),
    legacy_header_names: tuple[str, ...] = (),
    require_configured: bool = False,
):
    return require_internal_api_token_compat(
        token_keys=token_keys,
        legacy_header_names=legacy_header_names,
        require_configured=require_configured,
    )


def ensure_admin_console_action_token() -> str:
    token = _normalized_text(session.get(ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY))
    if token:
        return token
    token = secrets.token_urlsafe(24)
    session[ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY] = token
    session.modified = True
    return token


def validate_admin_console_action_token() -> str:
    expected = ensure_admin_console_action_token()
    json_payload = request.get_json(silent=True) or {}
    provided = (
        _normalized_text(request.form.get("admin_action_token"))
        or _normalized_text(request.values.get("admin_action_token"))
        or _normalized_text(json_payload.get("admin_action_token"))
    )
    if provided and provided == expected:
        return ""
    return "后台动作令牌无效，请刷新页面后重试"
