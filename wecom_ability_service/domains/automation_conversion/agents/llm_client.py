from __future__ import annotations

import json
import time
import uuid
from typing import Any

import requests
from flask import current_app

from ....infra.settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_EXECUTION_MODEL,
    DEFAULT_DEEPSEEK_ROUTER_MODEL,
    DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
    get_setting,
)
from .. import repo


class DeepSeekClientError(RuntimeError):
    pass


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_bool(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _setting_int(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def get_deepseek_runtime_config() -> dict[str, Any]:
    return {
        "enabled": _setting_bool("DEEPSEEK_ENABLED", default=False),
        "api_key": _setting_text("DEEPSEEK_API_KEY"),
        "base_url": _setting_text("DEEPSEEK_BASE_URL", default=DEFAULT_DEEPSEEK_BASE_URL) or DEFAULT_DEEPSEEK_BASE_URL,
        "router_model": _setting_text("DEEPSEEK_ROUTER_MODEL", default=DEFAULT_DEEPSEEK_ROUTER_MODEL) or DEFAULT_DEEPSEEK_ROUTER_MODEL,
        "execution_model": _setting_text("DEEPSEEK_EXECUTION_MODEL", default=DEFAULT_DEEPSEEK_EXECUTION_MODEL)
        or DEFAULT_DEEPSEEK_EXECUTION_MODEL,
        "timeout_seconds": _setting_int(
            "DEEPSEEK_TIMEOUT_SECONDS",
            default=DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
            minimum=1,
        ),
    }


def _selected_model(agent_code: str, *, explicit_model: str = "") -> str:
    normalized_explicit = _normalized_text(explicit_model)
    if normalized_explicit:
        return normalized_explicit
    config = get_deepseek_runtime_config()
    if _normalized_text(agent_code) == "central_router_agent":
        return _normalized_text(config["router_model"]) or DEFAULT_DEEPSEEK_ROUTER_MODEL
    return _normalized_text(config["execution_model"]) or DEFAULT_DEEPSEEK_EXECUTION_MODEL


def _request_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_normalized_text(api_key)}",
        "Content-Type": "application/json",
    }


def _log_call(
    *,
    agent_code: str,
    model_name: str,
    request_id: str,
    status: str,
    latency_ms: int,
    error_message: str = "",
) -> None:
    repo.insert_agent_llm_call_log(
        {
            "agent_code": _normalized_text(agent_code),
            "model_name": _normalized_text(model_name),
            "request_id": _normalized_text(request_id),
            "status": _normalized_text(status),
            "latency_ms": int(latency_ms),
            "error_message": _normalized_text(error_message),
        }
    )


def call_deepseek_agent(
    *,
    agent_code: str,
    system_prompt: str,
    user_input: str,
    json_output: bool = False,
    model_name: str = "",
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    started_at = time.perf_counter()
    config = get_deepseek_runtime_config()
    selected_model = _selected_model(agent_code, explicit_model=model_name)
    if not config["enabled"]:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=request_id,
            status="disabled",
            latency_ms=latency_ms,
            error_message="deepseek_disabled",
        )
        raise DeepSeekClientError("deepseek_disabled")
    if not _normalized_text(config["api_key"]):
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=request_id,
            status="not_configured",
            latency_ms=latency_ms,
            error_message="deepseek_api_key_not_configured",
        )
        raise DeepSeekClientError("deepseek_api_key_not_configured")

    request_payload: dict[str, Any] = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": _normalized_text(system_prompt)},
            {"role": "user", "content": _normalized_text(user_input)},
        ],
        "stream": False,
    }
    if json_output:
        request_payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            f"{_normalized_text(config['base_url']).rstrip('/')}/chat/completions",
            headers=_request_headers(_normalized_text(config["api_key"])),
            json=request_payload,
            timeout=int(config["timeout_seconds"]),
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
    except requests.RequestException as exc:
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=request_id,
            status="request_error",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            error_message=str(exc),
        )
        raise DeepSeekClientError(str(exc)) from exc

    response_request_id = _normalized_text(getattr(response, "headers", {}).get("x-request-id")) or request_id
    try:
        response_data = response.json()
    except ValueError as exc:
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=response_request_id,
            status="invalid_response",
            latency_ms=latency_ms,
            error_message="invalid_json_response",
        )
        raise DeepSeekClientError("invalid_json_response") from exc

    if int(response.status_code) >= 400:
        error_message = _normalized_text((response_data.get("error") or {}).get("message")) or _normalized_text(response.text)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=response_request_id,
            status="http_error",
            latency_ms=latency_ms,
            error_message=error_message or f"http_status_{int(response.status_code)}",
        )
        raise DeepSeekClientError(error_message or f"http_status_{int(response.status_code)}")

    message = dict(((response_data.get("choices") or [{}])[0].get("message") or {}))
    content = _normalized_text(message.get("content"))
    parsed_output: Any = None
    if json_output:
        try:
            parsed_output = json.loads(content or "{}")
        except ValueError as exc:
            _log_call(
                agent_code=agent_code,
                model_name=selected_model,
                request_id=response_request_id,
                status="parse_error",
                latency_ms=latency_ms,
                error_message="invalid_json_output",
            )
            raise DeepSeekClientError("invalid_json_output") from exc

    _log_call(
        agent_code=agent_code,
        model_name=selected_model,
        request_id=response_request_id,
        status="success",
        latency_ms=latency_ms,
    )
    return {
        "ok": True,
        "request_id": response_request_id,
        "model_name": selected_model,
        "content": content,
        "parsed_output": parsed_output,
        "latency_ms": latency_ms,
        "response_json": response_data,
    }


def test_deepseek_connection() -> dict[str, Any]:
    return call_deepseek_agent(
        agent_code="central_router_agent",
        system_prompt="You are a health check assistant. Return a JSON object with ok=true.",
        user_input='Please return {"ok": true, "message": "deepseek connected"}',
        json_output=True,
        model_name="",
    )
