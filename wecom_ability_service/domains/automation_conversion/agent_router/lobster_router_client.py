from __future__ import annotations

from typing import Any

import requests
from flask import current_app

from ....infra.settings import (
    DEFAULT_LOBSTER_CENTRAL_ROUTER_URL,
    get_setting,
)
from .contracts import RouterMessage, RouterRequestPayload
from .exceptions import (
    LobsterRouterConfigError,
    LobsterRouterHTTPError,
    LobsterRouterRequestError,
)


DEFAULT_LOBSTER_CENTRAL_ROUTER_TIMEOUT_SECONDS = 15


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_int(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def get_lobster_router_runtime_config() -> dict[str, Any]:
    return {
        "url": _setting_text("LOBSTER_CENTRAL_ROUTER_URL", default=DEFAULT_LOBSTER_CENTRAL_ROUTER_URL)
        or DEFAULT_LOBSTER_CENTRAL_ROUTER_URL,
        "token": _setting_text("LOBSTER_CENTRAL_ROUTER_TOKEN"),
        "timeout_seconds": _setting_int(
            "LOBSTER_CENTRAL_ROUTER_TIMEOUT_SECONDS",
            default=DEFAULT_LOBSTER_CENTRAL_ROUTER_TIMEOUT_SECONDS,
            minimum=1,
        ),
    }


def _request_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    normalized_token = _normalized_text(token)
    if normalized_token:
        headers["Authorization"] = f"Bearer {normalized_token}"
    return headers


def build_router_request_payload(
    *,
    external_userid: str,
    messages: list[RouterMessage],
) -> RouterRequestPayload:
    return {
        "external_userid": _normalized_text(external_userid),
        "messages": [
            {
                "role": _normalized_text(item.get("role")),
                "content": _normalized_text(item.get("content")),
                "timestamp": _normalized_text(item.get("timestamp")),
            }
            for item in messages
        ],
    }


def post_router_request(payload: RouterRequestPayload) -> dict[str, Any]:
    config = get_lobster_router_runtime_config()
    request_url = _normalized_text(config.get("url"))
    if not request_url:
        raise LobsterRouterConfigError("lobster_central_router_url_not_configured")
    try:
        response = requests.post(
            request_url,
            headers=_request_headers(_normalized_text(config.get("token"))),
            json=payload,
            timeout=int(config.get("timeout_seconds") or DEFAULT_LOBSTER_CENTRAL_ROUTER_TIMEOUT_SECONDS),
        )
    except requests.RequestException as exc:
        raise LobsterRouterRequestError(str(exc)) from exc
    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {}
    if int(response.status_code) >= 400:
        error_message = _normalized_text((response_payload.get("error") or {}).get("message")) or _normalized_text(response.text)
        raise LobsterRouterHTTPError(error_message or f"http_status_{int(response.status_code)}")
    return {
        "status_code": int(response.status_code),
        "response_payload": response_payload,
        "headers": dict(getattr(response, "headers", {}) or {}),
    }
