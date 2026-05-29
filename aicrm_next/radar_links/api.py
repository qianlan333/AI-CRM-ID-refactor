from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .application import (
    CompleteRadarOAuthCallbackCommand,
    CreateRadarLinkCommand,
    GetRadarLinkQuery,
    GetRadarLinkStatsQuery,
    ListRadarLinkEventsQuery,
    ListRadarLinksQuery,
    ResolveRadarLandingQuery,
    SetRadarLinkEnabledCommand,
    StartRadarOAuthQuery,
    UpdateRadarLinkCommand,
)
from .dto import RadarLinkCreateRequest, RadarLinkUpdateRequest

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, RepositoryProviderError):
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "fixture_repository_blocked_in_production",
                "detail": str(exc),
            },
        ) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _identity_from_request(request: Request) -> dict[str, str]:
    return {
        "openid": str(request.query_params.get("openid") or request.cookies.get("openid") or "").strip(),
        "unionid": str(request.query_params.get("unionid") or request.cookies.get("unionid") or "").strip(),
        "external_userid": str(request.query_params.get("external_userid") or request.cookies.get("external_userid") or "").strip(),
    }


def _request_meta(request: Request) -> dict[str, str]:
    return {
        "user_agent": str(request.headers.get("user-agent") or ""),
        "ip": request.client.host if request.client else "",
    }


@router.get("/api/admin/radar-links")
def list_radar_links(request: Request, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    try:
        return ListRadarLinksQuery()(base_url=_base_url(request), limit=limit, offset=offset)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/radar-links")
def create_radar_link(request: Request, payload: RadarLinkCreateRequest) -> dict[str, Any]:
    try:
        return CreateRadarLinkCommand()(payload, base_url=_base_url(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/radar-links/{link_id}")
def get_radar_link(request: Request, link_id: int) -> dict[str, Any]:
    try:
        return GetRadarLinkQuery()(link_id, base_url=_base_url(request))
    except Exception as exc:
        _raise_http(exc)


@router.patch("/api/admin/radar-links/{link_id}")
def update_radar_link(request: Request, link_id: int, payload: RadarLinkUpdateRequest) -> dict[str, Any]:
    try:
        return UpdateRadarLinkCommand()(link_id, payload, base_url=_base_url(request))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/radar-links/{link_id}/enable")
def enable_radar_link(request: Request, link_id: int) -> dict[str, Any]:
    try:
        return SetRadarLinkEnabledCommand()(link_id, enabled=True, base_url=_base_url(request))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/radar-links/{link_id}/disable")
def disable_radar_link(request: Request, link_id: int) -> dict[str, Any]:
    try:
        return SetRadarLinkEnabledCommand()(link_id, enabled=False, base_url=_base_url(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/radar-links/{link_id}/stats")
def get_radar_link_stats(link_id: int) -> dict[str, Any]:
    try:
        return GetRadarLinkStatsQuery()(link_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/radar-links/{link_id}/events")
def list_radar_link_events(link_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    try:
        return ListRadarLinkEventsQuery()(link_id, limit=limit, offset=offset)
    except Exception as exc:
        _raise_http(exc)


@router.get("/r/{code}")
def radar_public_redirect(request: Request, code: str):
    try:
        result = ResolveRadarLandingQuery()(code, identity=_identity_from_request(request), request_meta=_request_meta(request))
    except Exception as exc:
        _raise_http(exc)
    if result["action"] == "oauth_start":
        return RedirectResponse(url=result["oauth_start_url"], status_code=302)
    return RedirectResponse(url=result["redirect_url"], status_code=302)


@router.get("/api/h5/radar/oauth/start")
def radar_oauth_start(
    state: str | None = None,
    code: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
    external_userid: str | None = None,
):
    try:
        result = StartRadarOAuthQuery()(state=state, code=code, openid=openid, unionid=unionid, external_userid=external_userid)
    except Exception as exc:
        _raise_http(exc)
    return RedirectResponse(url=result["redirect_url"], status_code=302)


@router.get("/api/h5/radar/oauth/callback")
def radar_oauth_callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
    external_userid: str | None = None,
):
    try:
        result = CompleteRadarOAuthCallbackCommand()(
            state=state,
            code=code,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
            request_meta=_request_meta(request),
        )
    except Exception as exc:
        _raise_http(exc)
    return RedirectResponse(url=result["redirect_url"], status_code=302)
