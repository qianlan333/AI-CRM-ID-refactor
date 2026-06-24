from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from aicrm_next.admin_auth.guards import admin_api_auth_error

from .service import AudiencePackageService

router = APIRouter()

_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
}


@router.get("/api/admin/ai-audience/packages", name="api.admin_ai_audience_packages")
def admin_ai_audience_packages(request: Request) -> JSONResponse:
    if auth := admin_api_auth_error(request):
        return auth
    try:
        payload = AudiencePackageService().list_admin_package_summaries(limit=200)
        status_code = 200
    except Exception as exc:
        payload = {"ok": False, "error": "ai_audience_packages_unavailable", "detail": str(exc), "items": [], "total": 0}
        status_code = 500
    return JSONResponse(jsonable_encoder(payload), status_code=status_code, headers=_HEADERS)
