from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    CompleteWechatOAuthCallbackCommand,
    DeleteQuestionnaireCommand,
    ExportQuestionnaireQuery,
    GetPublicQuestionnaireQuery,
    GetQuestionnaireDetailQuery,
    GetQuestionnairePreflightQuery,
    GetSubmissionResultQuery,
    LatestSubmitDebugQuery,
    ListQuestionnairesQuery,
    SetQuestionnaireEnabledCommand,
    StartWechatOAuthQuery,
    SubmitQuestionnaireCommand,
    UpsertQuestionnaireCommand,
)
from .dto import OAuthCallbackRequest, OAuthStartRequest, QuestionnaireSubmitRequest, QuestionnaireUpsertRequest

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/questionnaires")
def list_questionnaires(limit: int = 50, offset: int = 0) -> dict:
    return ListQuestionnairesQuery()(limit=limit, offset=offset)


@router.get("/api/admin/questionnaires/preflight")
def questionnaire_preflight() -> dict:
    return GetQuestionnairePreflightQuery()()


@router.post("/api/admin/questionnaires")
def create_questionnaire(payload: QuestionnaireUpsertRequest) -> dict:
    try:
        return UpsertQuestionnaireCommand()(payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}")
def get_questionnaire(questionnaire_id: int) -> dict:
    try:
        return GetQuestionnaireDetailQuery()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/questionnaires/{questionnaire_id}")
def update_questionnaire(questionnaire_id: int, payload: QuestionnaireUpsertRequest) -> dict:
    try:
        return UpsertQuestionnaireCommand()(payload, questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/questionnaires/{questionnaire_id}/disable")
def disable_questionnaire(questionnaire_id: int, payload: dict | None = None) -> dict:
    try:
        enabled = not bool((payload or {}).get("is_disabled", True))
        return SetQuestionnaireEnabledCommand()(questionnaire_id, enabled=enabled)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/questionnaires/{questionnaire_id}/enable")
def enable_questionnaire(questionnaire_id: int) -> dict:
    try:
        return SetQuestionnaireEnabledCommand()(questionnaire_id, enabled=True)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/questionnaires/{questionnaire_id}")
def delete_questionnaire(questionnaire_id: int) -> dict:
    try:
        return DeleteQuestionnaireCommand()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/export")
def export_questionnaire(questionnaire_id: int) -> dict:
    try:
        return ExportQuestionnaireQuery()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug")
def latest_submit_debug(questionnaire_id: int) -> dict:
    try:
        return LatestSubmitDebugQuery()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/h5/questionnaires/{slug}")
def public_get_questionnaire(slug: str) -> dict:
    try:
        return GetPublicQuestionnaireQuery()(slug)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/h5/questionnaires/{slug}/submit")
def public_submit_questionnaire(slug: str, payload: QuestionnaireSubmitRequest) -> dict:
    try:
        return SubmitQuestionnaireCommand()(slug, payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/h5/questionnaires/{slug}/result/{submission_id}")
def public_submission_result(slug: str, submission_id: str) -> dict:
    try:
        return GetSubmissionResultQuery()(slug, submission_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/h5/wechat/oauth/start")
def wechat_oauth_start(
    slug: str | None = None,
    state: str | None = None,
    redirect: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
    external_userid: str | None = None,
) -> dict:
    return StartWechatOAuthQuery()(
        OAuthStartRequest(
            slug=slug,
            state=state,
            redirect=redirect,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
    )


@router.get("/api/h5/wechat/oauth/callback")
def wechat_oauth_callback(
    state: str | None = None,
    redirect: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
    external_userid: str | None = None,
) -> dict:
    return CompleteWechatOAuthCallbackCommand()(
        OAuthCallbackRequest(
            state=state,
            redirect=redirect,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
    )


@router.get("/s/{slug}", response_class=HTMLResponse)
def public_questionnaire_h5_page(request: Request, slug: str):
    try:
        payload = GetPublicQuestionnaireQuery()(slug)
    except Exception as exc:
        _raise_http(exc)
    questionnaire = payload["questionnaire"]
    page_state = {
        "mode": "questionnaire",
        "slug": slug,
        "title": questionnaire["title"],
        "description": questionnaire.get("description") or "",
        "env_notice": "AI-CRM Next fake OAuth 模式：真实微信 OAuth 尚未接入。",
        "oauth_start_url": f"/api/h5/wechat/oauth/start?slug={slug}",
        "submit_url": f"/api/h5/questionnaires/{slug}/submit",
        "api_url": f"/api/h5/questionnaires/{slug}",
        "diagnostics_url": "",
        "submitted_url": f"/s/{slug}/submitted",
        "request_hints": {},
        "initial_questionnaire": {"questions": payload["questions"]},
        "answer_display_mode": "all",
        "prefill_fields": {},
        "form_error": "",
    }
    return templates.TemplateResponse(
        request,
        "questionnaire_h5_page.html",
        {"request": request, "page_state": page_state},
    )


@router.get("/s/{slug}/submitted", response_class=HTMLResponse)
def public_questionnaire_submitted(request: Request, slug: str):
    return templates.TemplateResponse(request, "questionnaire_h5_submitted.html", {"request": request})
