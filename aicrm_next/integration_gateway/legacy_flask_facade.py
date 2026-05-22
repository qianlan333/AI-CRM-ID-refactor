from __future__ import annotations

import json
import importlib
import logging
import os
from functools import lru_cache
from typing import Iterable

from fastapi import Request
from fastapi.responses import Response

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
    dry_run_response = _probe_dry_run_response(request)
    if dry_run_response is not None:
        return dry_run_response

    body = await request.body()
    query_string = request.url.query.encode("utf-8")
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
    )
    return Response(
        content=legacy_response.get_data(),
        status_code=legacy_response.status_code,
        headers=_filtered_headers(legacy_response.headers.items()),
        media_type=legacy_response.mimetype or None,
    )
