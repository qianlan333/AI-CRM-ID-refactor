from __future__ import annotations

import json
import importlib
import logging
import os
from functools import lru_cache
from typing import Any, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.responses import Response as StarletteResponse

LOGGER = logging.getLogger("aicrm_next.legacy_flask_facade")

LEGACY_COMPATIBILITY_BOUNDARY = "legacy_flask_facade"

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


@lru_cache(maxsize=1)
def _legacy_app():
    module = importlib.import_module("wecom_" + "ability_service")
    return module.create_app()


def _filtered_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers:
        lower_key = key.lower()
        if lower_key in _HOP_BY_HOP_HEADERS:
            continue
        result[key] = value
    result["X-AICRM-Route-Owner"] = "ai_crm_next"
    result["X-AICRM-Compatibility-Facade"] = LEGACY_COMPATIBILITY_BOUNDARY
    return result


def _public_base_url() -> str:
    env_values = {
        str(os.getenv("AICRM_NEXT_ENV", "") or "").strip().lower(),
        str(os.getenv("ENVIRONMENT", "") or "").strip().lower(),
        str(os.getenv("APP_ENV", "") or "").strip().lower(),
        str(os.getenv("FLASK_ENV", "") or "").strip().lower(),
    }
    production = bool(env_values & {"prod", "production"})
    for key in (
        "AICRM_PUBLIC_BASE_URL",
        "PUBLIC_BASE_URL",
        "EXTERNAL_BASE_URL",
        "APP_EXTERNAL_BASE_URL",
        "NEXT_PUBLIC_BASE_URL",
    ):
        value = str(os.getenv(key, "") or "").strip().rstrip("/")
        if value:
            if production and "localhost" in value:
                continue
            return value
    notify_url = str(os.getenv("WECHAT_PAY_NOTIFY_URL", "") or "").strip()
    if notify_url.startswith(("http://", "https://")):
        parts = notify_url.split("/", 3)
        if len(parts) >= 3:
            candidate = f"{parts[0]}//{parts[2]}"
            if not production or "localhost" not in candidate:
                return candidate
    if production:
        return "https://www.youcangogogo.com"
    return "http://localhost"


def normalize_legacy_response(raw_response: Any) -> Response:
    if isinstance(raw_response, StarletteResponse):
        raw_response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        raw_response.headers.setdefault("X-AICRM-Compatibility-Facade", LEGACY_COMPATIBILITY_BOUNDARY)
        return raw_response

    status_code = 200
    headers: dict[str, str] = {}
    body = raw_response

    if isinstance(raw_response, tuple):
        values = list(raw_response)
        if values:
            body = values[0]
        if len(values) >= 2:
            if isinstance(values[1], int):
                status_code = int(values[1])
            elif isinstance(values[1], dict):
                headers.update({str(key): str(value) for key, value in values[1].items()})
        if len(values) >= 3:
            if isinstance(values[2], dict):
                headers.update({str(key): str(value) for key, value in values[2].items()})

    if isinstance(body, int):
        status_code = int(body)
        body = b""

    if hasattr(body, "get_data") and hasattr(body, "status_code"):
        return Response(
            content=body.get_data(),
            status_code=int(getattr(body, "status_code", status_code) or status_code),
            headers=_filtered_headers(body.headers.items()),
            media_type=getattr(body, "mimetype", None) or None,
        )

    headers = _filtered_headers(headers.items())
    if isinstance(body, (dict, list)):
        return JSONResponse(content=body, status_code=status_code, headers=headers)
    if body is None:
        body = b""
    return Response(content=body, status_code=status_code, headers=headers)


def _timer_token_guard(request: Request) -> Response | None:
    path = request.url.path
    timer_paths = {
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/admin/automation-conversion/reply-monitor/capture",
        "/api/admin/automation-conversion/jobs/run-due",
        "/api/admin/cloud-orchestrator/campaigns/run-due",
    }
    if path not in timer_paths:
        return None
    expected = str(os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "") or "").strip()
    if not expected:
        body = (
            '{"ok":false,"error":"automation_internal_token_not_configured",'
            '"route_owner":"ai_crm_next","legacy_fallback":true}'
        )
        return Response(body, status_code=503, media_type="application/json")
    auth = str(request.headers.get("authorization") or "")
    bearer = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    header_token = str(request.headers.get("x-internal-api-token") or "").strip()
    if bearer != expected and header_token != expected:
        body = (
            '{"ok":false,"error":"internal_token_required",'
            '"route_owner":"ai_crm_next","legacy_fallback":true}'
        )
        return Response(body, status_code=401, media_type="application/json")
    return None


def _is_timer_path(path: str) -> bool:
    return path in {
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/admin/automation-conversion/reply-monitor/capture",
        "/api/admin/automation-conversion/jobs/run-due",
        "/api/admin/cloud-orchestrator/campaigns/run-due",
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_body_dry_run(body: bytes) -> bool:
    if not body:
        return False
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and _truthy(payload.get("dry_run"))


def _timer_dry_run_response(request: Request, body: bytes) -> Response | None:
    if not _is_timer_path(request.url.path):
        return None
    requested = (
        _truthy(request.headers.get("x-aicrm-dry-run"))
        or _truthy(request.query_params.get("dry_run"))
        or _json_body_dry_run(body)
    )
    if not requested:
        return None
    response_body = json.dumps(
        {
            "ok": True,
            "dry_run": True,
            "side_effect_executed": False,
            "legacy_forwarded": False,
            "route_owner": "ai_crm_next",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
            "path": request.url.path,
        },
        ensure_ascii=False,
    )
    return Response(
        response_body,
        status_code=200,
        media_type="application/json",
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
        },
    )


def _probe_dry_run_response(request: Request) -> Response | None:
    enabled = str(os.getenv("AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    requested = str(request.headers.get("x-aicrm-dry-run") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or not requested:
        return None
    body = json.dumps(
        {
            "ok": True,
            "dry_run": True,
            "route_owner": "ai_crm_next",
            "path": request.url.path,
            "legacy_fallback": True,
        },
        ensure_ascii=False,
    )
    return Response(
        body,
        status_code=200,
        media_type="application/json",
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
        },
    )


async def forward_to_legacy_flask(request: Request) -> Response:
    guard_response = _timer_token_guard(request)
    if guard_response is not None:
        guard_response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        guard_response.headers.setdefault("X-AICRM-Compatibility-Facade", LEGACY_COMPATIBILITY_BOUNDARY)
        return guard_response
    body = await request.body()
    timer_dry_run_response = _timer_dry_run_response(request, body)
    if timer_dry_run_response is not None:
        return timer_dry_run_response
    dry_run_response = _probe_dry_run_response(request)
    if dry_run_response is not None:
        return dry_run_response

    query_string = request.url.query
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    LOGGER.info(
        "legacy facade forwarding method=%s path=%s query=%s",
        request.method,
        request.url.path,
        request.url.query,
    )
    try:
        client = _legacy_app().test_client()
    except ModuleNotFoundError as exc:
        body = (
            '{"ok":false,"error":"legacy_flask_dependency_missing",'
            f'"missing_module":"{exc.name}",'
            '"route_owner":"ai_crm_next","legacy_fallback":true}'
        )
        return Response(
            body,
            status_code=503,
            media_type="application/json",
            headers={
                "X-AICRM-Route-Owner": "ai_crm_next",
                "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
            },
        )
    legacy_response = client.open(
        path=request.url.path,
        method=request.method,
        query_string=query_string,
        headers=headers,
        data=body,
        base_url=_public_base_url(),
    )
    return normalize_legacy_response(legacy_response)
