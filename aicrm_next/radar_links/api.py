from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .application import (
    CompleteRadarOAuthCallbackCommand,
    CreateRadarLinkCommand,
    GetRadarContentResourceQuery,
    GetRadarLinkQuery,
    GetRadarLinkNewOptionsQuery,
    GetRadarLinkShareQuery,
    GetRadarLinkStatsQuery,
    GetRadarViewerPageQuery,
    ListRadarLinkEventsQuery,
    ListRadarLinksQuery,
    RecordRadarContentEventCommand,
    ResolveRadarLandingQuery,
    SetRadarLinkEnabledCommand,
    StartRadarOAuthQuery,
    UpdateRadarLinkCommand,
)
from aicrm_next.media_library.application import UploadAttachmentCommand, UploadImageCommand
from .dto import RadarLinkCreateRequest, RadarLinkUpdateRequest

router = APIRouter()
RADAR_VIEWER_COOKIE = "aicrm_radar_viewer"


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, RepositoryProviderError):
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "radar_links_repository_unavailable",
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
        "referer": str(request.headers.get("referer") or ""),
        "query_params_json": dict(request.query_params),
    }


def _redirect_with_viewer_cookie(url: str, token: str = "") -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=302)
    if token:
        response.set_cookie(
            RADAR_VIEWER_COOKIE,
            token,
            max_age=2 * 60 * 60,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    return response


@router.get("/api/admin/radar-links")
def list_radar_links(request: Request, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    try:
        return ListRadarLinksQuery()(base_url=_base_url(request), limit=limit, offset=offset)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/radar-links/new/options")
def get_radar_link_new_options() -> dict[str, Any]:
    try:
        return GetRadarLinkNewOptionsQuery()()
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


@router.get("/api/admin/radar-links/{link_id}/share")
def get_radar_link_share(request: Request, link_id: int) -> dict[str, Any]:
    try:
        return GetRadarLinkShareQuery()(link_id, base_url=_base_url(request))
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
def list_radar_link_events(
    request: Request,
    link_id: int,
    limit: int = 100,
    offset: int = 0,
    stage: str = "",
    start_at: str = "",
    end_at: str = "",
) -> dict[str, Any]:
    try:
        return ListRadarLinkEventsQuery()(
            link_id,
            limit=limit,
            offset=offset,
            stage=stage,
            start_at=start_at,
            end_at=end_at,
            base_url=_base_url(request),
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/r/{code}")
def radar_public_redirect(request: Request, code: str):
    try:
        result = ResolveRadarLandingQuery()(
            code,
            identity=_identity_from_request(request),
            request_meta=_request_meta(request),
            viewer_session=request.cookies.get(RADAR_VIEWER_COOKIE),
        )
    except Exception as exc:
        _raise_http(exc)
    if result["action"] == "oauth_start":
        return RedirectResponse(url=result["oauth_start_url"], status_code=302)
    return _redirect_with_viewer_cookie(str(result["redirect_url"]), str(result.get("viewer_session_token") or ""))


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
    return _redirect_with_viewer_cookie(str(result["redirect_url"]), str(result.get("viewer_session_token") or ""))


@router.get("/radar/view/{code}")
def radar_content_view(request: Request, code: str):
    try:
        result = GetRadarViewerPageQuery()(code, viewer_session=request.cookies.get(RADAR_VIEWER_COOKIE), request_meta=_request_meta(request))
    except Exception as exc:
        _raise_http(exc)
    radar_link = result["radar_link"]
    title = html.escape(str(radar_link.get("title") or "内容预览"), quote=True)
    target_type = str(result.get("target_type") or "")
    resource_url = html.escape(f"/api/h5/radar-contents/{code}/{'image' if target_type == 'image' else 'pdf'}", quote=True)
    if target_type == "image":
        body = f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f6f7fb; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 14px 16px; border-bottom: 1px solid #e5e7eb; background: rgba(255, 255, 255, 0.96); font-size: 16px; font-weight: 800; }}
    main {{ min-height: calc(100vh - 50px); display: flex; align-items: flex-start; justify-content: center; padding: 0; }}
    img {{ display: block; width: 100%; max-width: 960px; height: auto; background: #fff; }}
    .fallback {{ display: none; width: 100%; padding: 40px 18px; color: #6b7280; text-align: center; }}
  </style>
</head>
<body>
  <header>{title}</header>
  <main>
    <img src="{resource_url}" alt="{title}" onerror="this.style.display='none';document.querySelector('.fallback').style.display='block';">
    <div class="fallback">内容暂时无法查看</div>
  </main>
</body>
</html>
"""
    else:
        body = f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f6f7fb; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 12px 16px; border-bottom: 1px solid #e5e7eb; background: rgba(255, 255, 255, 0.96); font-size: 16px; font-weight: 800; }}
    .viewer {{ min-height: calc(100vh - 48px); padding: 10px 0 24px; background: #eef1f6; }}
    .page {{ display: block; width: calc(100vw - 16px); max-width: 860px; height: auto; margin: 0 auto 10px; background: #fff; box-shadow: 0 1px 6px rgba(15, 23, 42, .12); }}
    .state {{ padding: 40px 18px; color: #6b7280; text-align: center; }}
    .state[hidden] {{ display: none; }}
  </style>
</head>
<body>
  <header>{title}</header>
  <main class="viewer">
    <div class="state" data-pdf-state>内容加载中...</div>
    <div data-pdf-pages></div>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js"></script>
  <script>
    (function () {{
      var state = document.querySelector("[data-pdf-state]");
      var pages = document.querySelector("[data-pdf-pages]");
      function fail() {{
        if (state) {{
          state.hidden = false;
          state.textContent = "内容暂时无法查看";
        }}
      }}
      function fitScale(page) {{
        var viewport = page.getViewport({{scale: 1}});
        var width = Math.max(280, Math.min(window.innerWidth - 16, 860));
        return width / viewport.width;
      }}
      async function renderPage(pdf, pageNumber) {{
        var page = await pdf.getPage(pageNumber);
        var viewport = page.getViewport({{scale: fitScale(page)}});
        var canvas = document.createElement("canvas");
        var context = canvas.getContext("2d");
        canvas.className = "page";
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = Math.floor(viewport.width) + "px";
        canvas.style.height = Math.floor(viewport.height) + "px";
        pages.appendChild(canvas);
        await page.render({{canvasContext: context, viewport: viewport}}).promise;
      }}
      async function start() {{
        if (!window.pdfjsLib) {{
          fail();
          return;
        }}
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";
        try {{
          var response = await fetch("{resource_url}", {{credentials: "same-origin", cache: "no-store"}});
          if (!response.ok) throw new Error("pdf unavailable");
          var data = await response.arrayBuffer();
          var pdf = await window.pdfjsLib.getDocument({{data: data}}).promise;
          if (state) state.hidden = true;
          for (var i = 1; i <= pdf.numPages; i += 1) {{
            await renderPage(pdf, i);
          }}
        }} catch (err) {{
          fail();
        }}
      }}
      start();
    }})();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=body)


@router.get("/api/h5/radar-contents/{code}/image")
def radar_content_image(request: Request, code: str):
    try:
        result = GetRadarContentResourceQuery()(code, target_type="image", viewer_session=request.cookies.get(RADAR_VIEWER_COOKIE), request_meta=_request_meta(request))
    except Exception as exc:
        _raise_http(exc)
    return Response(
        content=result["content"],
        media_type=str(result.get("mime_type") or "image/png"),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/api/h5/radar-contents/{code}/pdf")
def radar_content_pdf(request: Request, code: str):
    try:
        result = GetRadarContentResourceQuery()(code, target_type="pdf", viewer_session=request.cookies.get(RADAR_VIEWER_COOKIE), request_meta=_request_meta(request))
    except Exception as exc:
        _raise_http(exc)
    file_name = str(result.get("file_name") or "content.pdf").replace('"', "")
    return Response(
        content=result["content"],
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{file_name}"', "Cache-Control": "private, max-age=300"},
    )


@router.post("/api/h5/radar-contents/{code}/events")
def radar_content_event(request: Request, code: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return RecordRadarContentEventCommand()(
            code,
            payload=payload,
            viewer_session=request.cookies.get(RADAR_VIEWER_COOKIE),
            request_meta=_request_meta(request),
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/radar-links/upload-image")
async def upload_radar_image(image: UploadFile = File(...), name: str = Form(""), tags: str = Form("")) -> dict[str, Any]:
    try:
        return UploadImageCommand()(
            file_bytes=await image.read(),
            file_name=image.filename or "image.png",
            content_type=image.content_type or "application/octet-stream",
            name=name,
            tags=tags,
            category="radar_content",
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/radar-links/upload-pdf")
async def upload_radar_pdf(pdf: UploadFile = File(...), name: str = Form(""), tags: str = Form("")) -> dict[str, Any]:
    try:
        return UploadAttachmentCommand()(
            file_bytes=await pdf.read(),
            file_name=pdf.filename or "content.pdf",
            content_type=pdf.content_type or "application/octet-stream",
            name=name,
            tags=tags,
        )
    except Exception as exc:
        _raise_http(exc)


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
    return _redirect_with_viewer_cookie(str(result["redirect_url"]), str(result.get("viewer_session_token") or ""))
