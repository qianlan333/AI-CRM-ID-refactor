from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_jobs.routes import ensure_admin_action_token, validate_admin_action_token
from aicrm_next.admin_shell import admin_path_for, shell_context

from .repo import build_external_effect_repository
from .service import ExternalEffectService
from .view_model import build_external_effect_diagnostics_payload, build_external_effect_jobs_payload, external_effect_filters
from .worker import ExternalEffectWorker

router = APIRouter()
ROUTE_OWNER = "ai_crm_next"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FRONTEND_COMPAT_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=[_TEMPLATES_DIR, _FRONTEND_COMPAT_TEMPLATES_DIR])


def _text(value: Any) -> str:
    return str(value or "").strip()


async def _payload(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception:
        return {}
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    headers = {
        "X-AICRM-Route-Owner": ROUTE_OWNER,
        "X-AICRM-Real-External-Call-Executed": "true" if bool(payload.get("real_external_call_executed")) else "false",
    }
    return JSONResponse(payload, status_code=status_code, headers=headers)


def _internal_token_error(request: Request) -> str:
    header = _text(request.headers.get("Authorization"))
    if not header.lower().startswith("bearer "):
        return "internal_token_required"
    expected = _text(os.getenv("AUTOMATION_INTERNAL_API_TOKEN"))
    if not expected:
        return "automation_internal_token_not_configured"
    actual = header.split(" ", 1)[1].strip()
    if not hmac.compare_digest(actual, expected):
        return "internal_token_required"
    return ""


def _action_or_internal_token_error(request: Request, payload: dict[str, Any]) -> str:
    internal_error = _internal_token_error(request)
    if not internal_error:
        return ""
    token = _text(request.headers.get("X-Admin-Action-Token")) or _text(payload.get("admin_action_token"))
    return validate_admin_action_token(token)


def _service() -> ExternalEffectService:
    return ExternalEffectService(build_external_effect_repository())


def _page_context(
    request: Request,
    *,
    page_notice: str = "",
    page_error: str = "",
    action_result: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = shell_context(
        request=request,
        page_title="External Effects",
        page_summary="统一外部动作队列的 shadow 任务、执行尝试和排障入口。",
        active_endpoint="api.admin_external_effects_page",
    )
    payload = build_external_effect_jobs_payload(params if params is not None else dict(request.query_params), service=_service())
    context.update(
        {
            "breadcrumbs": [{"label": "客户管理后台", "href": "/"}, {"label": "External Effects", "href": ""}],
            "external_effects": payload,
            "page_notice": page_notice,
            "page_error": page_error,
            "action_result": action_result or {},
            "admin_action_token": ensure_admin_action_token(),
            "url_for": admin_path_for,
        }
    )
    return context


def _page_params_from_form(form: Any, request: Request) -> dict[str, Any]:
    params = dict(request.query_params)
    for key in ("effect_type", "status", "target_type", "target_id", "business_type", "business_id", "trace_id", "job_id", "limit", "offset"):
        form_value = _text(form.get(key))
        if form_value:
            params[key] = form_value
        elif key in params and key not in {"job_id"}:
            params.pop(key, None)
    return params


@router.get("/admin/external-effects", name="api.admin_external_effects_page", response_class=HTMLResponse)
def admin_external_effects_page(request: Request):
    return templates.TemplateResponse(request, "admin_console/external_effects.html", _page_context(request))


@router.post("/admin/external-effects/actions", name="api.admin_external_effects_action", response_class=HTMLResponse)
async def admin_external_effects_action(request: Request):
    form = await request.form()
    params = _page_params_from_form(form, request)
    token_error = validate_admin_action_token(_text(form.get("admin_action_token")))
    if token_error:
        return templates.TemplateResponse(
            request,
            "admin_console/external_effects.html",
            _page_context(request, page_error=token_error, params=params),
        )

    action = _text(form.get("action"))
    try:
        repo = build_external_effect_repository()
        service = ExternalEffectService(repo)
        effect_types = [_text(form.get("effect_type"))] if _text(form.get("effect_type")) else None
        if action == "run-due-preview":
            result = ExternalEffectWorker(repo).preview_due(
                batch_size=_int(form.get("batch_size"), default=50, minimum=1),
                effect_types=effect_types,
            )
            result["route_owner"] = ROUTE_OWNER
            return templates.TemplateResponse(
                request,
                "admin_console/external_effects.html",
                _page_context(request, page_notice="run-due preview 已生成。", action_result=result, params=params),
            )
        if action == "run-due-dry-run":
            result = ExternalEffectWorker(repo).run_due(
                batch_size=_int(form.get("batch_size"), default=50, minimum=1),
                dry_run=True,
                effect_types=effect_types,
            )
            result["route_owner"] = ROUTE_OWNER
            result["real_external_call_executed"] = False
            return templates.TemplateResponse(
                request,
                "admin_console/external_effects.html",
                _page_context(request, page_notice="run-due dry-run 已完成。", action_result=result, params=params),
            )
        if action == "retry":
            job = service.retry(_int(form.get("job_id"), default=0, minimum=0, maximum=10**12))
            result = {"ok": bool(job), "job": job.to_dict() if job else None, "real_external_call_executed": False}
            notice = "任务已重新入队。" if job else "任务当前不可 retry。"
            return templates.TemplateResponse(
                request,
                "admin_console/external_effects.html",
                _page_context(request, page_notice=notice, action_result=result, params=params),
            )
        if action == "cancel":
            job = service.cancel(_int(form.get("job_id"), default=0, minimum=0, maximum=10**12))
            result = {"ok": bool(job), "job": job.to_dict() if job else None, "real_external_call_executed": False}
            notice = "任务已取消。" if job else "任务当前不可 cancel。"
            return templates.TemplateResponse(
                request,
                "admin_console/external_effects.html",
                _page_context(request, page_notice=notice, action_result=result, params=params),
            )
        return templates.TemplateResponse(
            request,
            "admin_console/external_effects.html",
            _page_context(request, page_error="未知 external effects 操作。", params=params),
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "admin_console/external_effects.html",
            _page_context(request, page_error=str(exc), params=params),
        )


@router.get("/api/admin/external-effects/jobs")
def list_external_effect_jobs(
    effect_type: str = "",
    status: str = "",
    target_type: str = "",
    target_id: str = "",
    business_type: str = "",
    business_id: str = "",
    trace_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return build_external_effect_jobs_payload(
        {
            "effect_type": effect_type,
            "status": status,
            "target_type": target_type,
            "target_id": target_id,
            "business_type": business_type,
            "business_id": business_id,
            "trace_id": trace_id,
            "limit": limit,
            "offset": offset,
        },
        service=_service(),
    )


@router.get("/api/admin/external-effects/diagnostics")
def external_effect_diagnostics(
    effect_type: str = "",
    status: str = "",
    target_type: str = "",
    target_id: str = "",
    business_type: str = "",
    business_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return build_external_effect_diagnostics_payload(
        external_effect_filters(
            {
                "effect_type": effect_type,
                "status": status,
                "target_type": target_type,
                "target_id": target_id,
                "business_type": business_type,
                "business_id": business_id,
                "trace_id": trace_id,
            }
        ),
        service=_service(),
    )


@router.get("/api/admin/external-effects/jobs/{job_id}")
def get_external_effect_job(job_id: int) -> JSONResponse:
    service = _service()
    job = service.get(job_id)
    if not job:
        return _json({"ok": False, "error": "external_effect_job_not_found", "route_owner": ROUTE_OWNER}, status_code=404)
    return _json(
        {
            "ok": True,
            "job": job.to_dict(),
            "attempts": [attempt.to_dict() for attempt in service.list_attempts(job_id)],
            "route_owner": ROUTE_OWNER,
        }
    )


@router.post("/api/admin/external-effects/run-due/preview")
async def preview_external_effect_run_due(request: Request) -> JSONResponse:
    token_error = _internal_token_error(request)
    if token_error:
        return _json({"ok": False, "error": token_error, "route_owner": ROUTE_OWNER, "real_external_call_executed": False}, status_code=401)
    payload = await _payload(request)
    repo = build_external_effect_repository()
    result = ExternalEffectWorker(repo).preview_due(
        batch_size=_int(payload.get("batch_size") or payload.get("limit"), default=50, minimum=1),
        effect_types=[_text(item) for item in payload.get("effect_types") or [] if _text(item)] or None,
    )
    result["route_owner"] = ROUTE_OWNER
    return _json(result)


@router.post("/api/admin/external-effects/run-due")
async def run_external_effect_due(request: Request) -> JSONResponse:
    token_error = _internal_token_error(request)
    if token_error:
        return _json({"ok": False, "error": token_error, "route_owner": ROUTE_OWNER, "real_external_call_executed": False}, status_code=401)
    payload = await _payload(request)
    dry_run = _bool(payload.get("dry_run"), default=True)
    repo = build_external_effect_repository()
    result = ExternalEffectWorker(repo).run_due(
        batch_size=_int(payload.get("batch_size") or payload.get("limit"), default=50, minimum=1),
        dry_run=dry_run,
        effect_types=[_text(item) for item in payload.get("effect_types") or [] if _text(item)] or None,
    )
    result["route_owner"] = ROUTE_OWNER
    result["real_external_call_executed"] = bool(result.get("real_external_call_executed")) and not dry_run
    return _json(result)


@router.post("/api/admin/external-effects/jobs/{job_id}/retry")
async def retry_external_effect_job(job_id: int, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error, "route_owner": ROUTE_OWNER}, status_code=401)
    job = _service().retry(job_id)
    if not job:
        return _json({"ok": False, "error": "external_effect_job_not_retryable", "route_owner": ROUTE_OWNER}, status_code=409)
    return _json({"ok": True, "job": job.to_dict(), "route_owner": ROUTE_OWNER})


@router.post("/api/admin/external-effects/jobs/{job_id}/cancel")
async def cancel_external_effect_job(job_id: int, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error, "route_owner": ROUTE_OWNER}, status_code=401)
    job = _service().cancel(job_id)
    if not job:
        return _json({"ok": False, "error": "external_effect_job_not_cancellable", "route_owner": ROUTE_OWNER}, status_code=409)
    return _json({"ok": True, "job": job.to_dict(), "route_owner": ROUTE_OWNER})
