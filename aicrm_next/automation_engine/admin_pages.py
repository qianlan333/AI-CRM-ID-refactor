from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from aicrm_next.admin_auth.guards import admin_page_auth_redirect

router = APIRouter()


def _retired_automation_program_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "legacy_automation_program_retired",
            "message": "旧自动化运营方案页面已退场，请使用 AI 自动化运营人群包。",
            "replacement": "/admin/automation-conversion",
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
        },
        status_code=410,
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Legacy-Automation-Retired": "true",
            "X-AICRM-Real-External-Call-Executed": "false",
            "X-AICRM-Automation-Runtime-Executed": "false",
        },
    )


@router.get("/admin/automation-conversion/legacy", name="api.admin_automation_conversion_legacy")
def admin_automation_conversion_legacy(request: Request) -> JSONResponse:
    if redirect := admin_page_auth_redirect(request):
        return redirect
    return _retired_automation_program_response()


@router.api_route(
    "/admin/automation-conversion/programs/{retired_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api.admin_automation_program_retired",
)
def retired_automation_program_page(retired_path: str = "") -> JSONResponse:
    del retired_path
    return _retired_automation_program_response()
