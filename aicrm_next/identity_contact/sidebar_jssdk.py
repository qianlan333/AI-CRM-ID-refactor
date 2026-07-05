from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from aicrm_next.integration_gateway.wecom_jssdk_adapter import (
    SidebarJSSDKConfigError,
    SidebarJSSDKInputError,
    build_sidebar_jssdk_config,
    normalize_jssdk_url,
)
from aicrm_next.shared.runtime import production_environment


router = APIRouter()
DEFAULT_SIDEBAR_JSSDK_ALLOWED_HOSTS = {"youcangogogo.com", "www.youcangogogo.com"}


@router.api_route("/api/sidebar/jssdk-config", methods=["GET", "HEAD", "OPTIONS"])
async def sidebar_jssdk_config(request: Request) -> Response:
    if request.method == "HEAD":
        return Response(status_code=204)
    if request.method == "OPTIONS":
        return JSONResponse(
            {
                "ok": True,
                "source_status": "next_jssdk_adapter",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "adapter_mode": "real_blocked",
                "real_external_call_executed": False,
                "allowed_methods": ["GET", "HEAD", "OPTIONS"],
            },
            status_code=200,
        )

    params = request.query_params
    corp_context = {
        "corp_id": str(params.get("corp_id") or params.get("corpId") or params.get("corpid") or "").strip(),
        "agent_id": str(params.get("agent_id") or params.get("agentId") or params.get("agentid") or "").strip(),
    }
    corp_context = {key: value for key, value in corp_context.items() if value}
    debug = str(params.get("debug") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        _validate_jssdk_url_host(request, str(params.get("url") or ""))
        payload = build_sidebar_jssdk_config(
            url=str(params.get("url") or ""),
            debug=debug,
            corp_context=corp_context,
        )
    except SidebarJSSDKInputError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "source_status": "input_error",
                "adapter_mode": "real_blocked",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "real_external_call_executed": False,
            },
            status_code=400,
        )
    except SidebarJSSDKConfigError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "source_status": "config_error",
                "adapter_mode": "real_enabled",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "real_external_call_executed": bool(getattr(exc, "real_external_call_executed", False)),
            },
            status_code=502,
        )
    return JSONResponse(jsonable_encoder(payload), status_code=200)


def _validate_jssdk_url_host(request: Request, raw_url: str) -> None:
    if not production_environment():
        return
    normalized_url = normalize_jssdk_url(raw_url)
    requested_host = str(urlparse(normalized_url).hostname or "").strip().lower()
    if not requested_host:
        raise SidebarJSSDKInputError("url host is required")
    allowed_hosts = _allowed_jssdk_hosts(request)
    if requested_host not in allowed_hosts:
        raise SidebarJSSDKInputError("url host is not allowed for sidebar jssdk signing")


def _allowed_jssdk_hosts(request: Request) -> set[str]:
    hosts = {
        *DEFAULT_SIDEBAR_JSSDK_ALLOWED_HOSTS,
        str(request.url.hostname or "").strip().lower(),
        str(request.headers.get("host") or "").split(":", 1)[0].strip().lower(),
    }
    configured = str(os.getenv("AICRM_SIDEBAR_JSSDK_ALLOWED_HOSTS") or "")
    hosts.update(item.strip().lower() for item in configured.split(",") if item.strip())
    return {host for host in hosts if host}
