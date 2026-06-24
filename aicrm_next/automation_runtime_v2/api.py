from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Legacy-Automation-Retired": "true",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
}


def _retired_runtime_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "automation_runtime_v2_retired",
            "message": "旧 automation_runtime_v2 阶段 / 任务编排 Runtime 已退场，请使用 AI Audience SQL 人群包链路。",
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
        },
        status_code=410,
        headers=_HEADERS,
    )


@router.api_route(
    "/api/automation-runtime/v2/{retired_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api.automation_runtime_v2_retired",
)
def automation_runtime_v2_retired(retired_path: str = "", payload: dict[str, Any] | None = None) -> JSONResponse:
    del retired_path, payload
    return _retired_runtime_response()
