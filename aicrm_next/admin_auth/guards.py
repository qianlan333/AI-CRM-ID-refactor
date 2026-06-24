from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from .service import SESSION_COOKIE, route_headers, safe_next_path, verify_session


def current_admin_session(request: Request) -> dict | None:
    return verify_session(request.cookies.get(SESSION_COOKIE))


def admin_api_auth_error(request: Request) -> JSONResponse | None:
    if current_admin_session(request):
        return None
    return JSONResponse(
        {
            "ok": False,
            "error": "admin_auth_required",
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        },
        status_code=401,
        headers=route_headers(),
    )


def admin_page_auth_redirect(request: Request) -> RedirectResponse | None:
    if current_admin_session(request):
        return None
    next_path = safe_next_path(str(request.url.path or "/admin"))
    if request.url.query:
        next_path = safe_next_path(f"{next_path}?{request.url.query}")
    return RedirectResponse(
        f"/login?next={quote(next_path, safe='/?:=&')}",
        status_code=302,
        headers=route_headers(),
    )
