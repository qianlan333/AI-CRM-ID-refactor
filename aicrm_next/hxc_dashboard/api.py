from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from aicrm_next.shared.errors import ContractError

from .application import CreateHxcBroadcastTaskCommand
from .dto import HxcBroadcastTaskRequest


router = APIRouter()


@router.post("/api/admin/hxc-dashboard/broadcast-tasks")
def create_hxc_broadcast_task(payload: dict[str, Any]) -> JSONResponse:
    try:
        request = HxcBroadcastTaskRequest.model_validate(payload)
        result = CreateHxcBroadcastTaskCommand()(request)
        return JSONResponse(result, status_code=int(result.get("status_code") or 200))
    except ValidationError:
        return _error("请求参数格式不正确", status_code=400)
    except ContractError as exc:
        return _error(str(exc), status_code=400)
    except Exception as exc:
        return _error(f"HXC 群发任务创建失败：{exc}", status_code=500)


def _error(message: str, *, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message, "detail": message}, status_code=status_code)
