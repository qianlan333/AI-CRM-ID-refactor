from __future__ import annotations

import secrets
from typing import Iterable

from flask import current_app, jsonify, request, session

from ..infra.settings import get_setting

ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY = "admin_console_action_token"


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _configured_internal_tokens(*token_keys: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for key in ("AUTOMATION_INTERNAL_API_TOKEN", *token_keys):
        normalized_key = _normalized_text(key)
        if not normalized_key:
            continue
        token = _normalized_text(get_setting(normalized_key)) or _normalized_text(current_app.config.get(normalized_key))
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _provided_internal_token(*, legacy_header_names: Iterable[str] = ()) -> str:
    auth_header = _normalized_text(request.headers.get("Authorization"))
    if auth_header.startswith("Bearer "):
        return _normalized_text(auth_header[7:])
    for header_name in legacy_header_names:
        token = _normalized_text(request.headers.get(_normalized_text(header_name)))
        if token:
            return token
    return ""


def require_internal_api_token(
    *,
    token_keys: tuple[str, ...] = (),
    legacy_header_names: tuple[str, ...] = (),
    require_configured: bool = False,
):
    expected_tokens = _configured_internal_tokens(*token_keys)
    if not expected_tokens:
        if require_configured:
            return jsonify({"ok": False, "error": "internal token not configured"}), 503
        return None
    provided_token = _provided_internal_token(legacy_header_names=legacy_header_names)
    if not provided_token:
        return jsonify({"ok": False, "error": "missing internal token"}), 401
    if provided_token not in expected_tokens:
        return jsonify({"ok": False, "error": "invalid internal token"}), 401
    return None


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
