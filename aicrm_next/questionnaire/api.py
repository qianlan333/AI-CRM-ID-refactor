from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.integration_gateway.legacy_flask_facade import (
    forward_to_legacy_flask,
    legacy_questionnaire_oauth_is_configured,
    legacy_questionnaire_session_identity,
)
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import production_data_ready

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
from aicrm_next.integration_gateway.legacy_questionnaire_facade import (
    LegacyQuestionnaireDataUnavailable,
    create_questionnaire_in_legacy,
    delete_questionnaire_in_legacy,
    export_questionnaire_from_legacy,
    get_public_questionnaire_from_legacy,
    get_questionnaire_detail_from_legacy,
    latest_submit_debug_from_legacy,
    list_questionnaires_from_legacy,
    set_questionnaire_enabled_in_legacy,
    update_questionnaire_in_legacy,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

_QUESTIONNAIRE_IDENTITY_HINT_FIELDS = (
    "respondent_key",
    "openid",
    "unionid",
    "external_userid",
)
_QUESTIONNAIRE_SOURCE_PARAM_FIELDS = (
    "source_channel",
    "campaign_id",
    "staff_id",
)
_QUESTIONNAIRE_META_FIELDS = _QUESTIONNAIRE_IDENTITY_HINT_FIELDS + _QUESTIONNAIRE_SOURCE_PARAM_FIELDS


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_excel_xml(headers: list[Any], rows: list[list[Any]]) -> bytes:
    def _render_row(values: list[Any]) -> str:
        cells = "".join(
            f'<Cell><Data ss:Type="String">{xml_escape(str(value or ""))}</Data></Cell>'
            for value in values
        )
        return f"<Row>{cells}</Row>"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:o="urn:schemas-microsoft-com:office:office"',
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
        '<Worksheet ss:Name="Questionnaire">',
        "<Table>",
        _render_row(headers),
    ]
    lines.extend(_render_row(row) for row in rows)
    lines.extend(["</Table>", "</Worksheet>", "</Workbook>"])
    return "\n".join(lines).encode("utf-8")


def _download_export_response(questionnaire_id: int, payload: dict[str, Any]) -> Response:
    export_payload = payload.get("export") if isinstance(payload.get("export"), dict) else payload
    filename = str(
        export_payload.get("filename") or f"questionnaire_{questionnaire_id}_submissions.xls"
    ).strip()
    headers = export_payload.get("headers")
    rows = export_payload.get("rows")
    if isinstance(headers, list) and isinstance(rows, list):
        content = _build_excel_xml(headers, rows)
        media_type = "application/vnd.ms-excel"
    else:
        if not filename.endswith(".json"):
            filename = f"questionnaire_{questionnaire_id}_submissions.json"
        content = json.dumps(export_payload, ensure_ascii=False, default=str).encode("utf-8")
        media_type = "application/json"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _questionnaire_payload_with_nested_questions(payload: dict[str, Any]) -> dict[str, Any]:
    questionnaire = payload.get("questionnaire")
    questions = payload.get("questions")
    if not isinstance(questionnaire, dict) or not isinstance(questions, list):
        return payload
    if isinstance(questionnaire.get("questions"), list):
        return payload
    return {**payload, "questionnaire": {**questionnaire, "questions": questions}}


def _public_questionnaire_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _questionnaire_payload_with_nested_questions(payload)
    questions = normalized.get("questions")
    if not isinstance(questions, list):
        return normalized
    public_questions = [
        {key: value for key, value in question.items() if key != "sidebar_profile_field"}
        if isinstance(question, dict)
        else question
        for question in questions
    ]
    questionnaire = normalized.get("questionnaire")
    if isinstance(questionnaire, dict):
        questionnaire = {
            **questionnaire,
            "questions": [
                {key: value for key, value in question.items() if key != "sidebar_profile_field"}
                if isinstance(question, dict)
                else question
                for question in questionnaire.get("questions", [])
            ],
        }
    return {**normalized, "questionnaire": questionnaire, "questions": public_questions}


def _is_wechat_browser(request: Request) -> bool:
    return "micromessenger" in str(request.headers.get("user-agent") or "").lower()


def _request_values(request: Request, fields: tuple[str, ...]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in fields:
        value = str(request.query_params.get(key) or "").strip()
        if value:
            payload[key] = value
    return payload


def _questionnaire_oauth_start_url(slug: str, source_params: dict[str, str]) -> str:
    query = {"slug": str(slug or "").strip(), **source_params}
    return f"/api/h5/wechat/oauth/start?{urlencode(query)}"


@router.get("/api/admin/questionnaires")
def list_questionnaires(limit: int = 50, offset: int = 0) -> dict:
    if production_data_ready():
        try:
            return list_questionnaires_from_legacy(limit=limit, offset=offset)
        except LegacyQuestionnaireDataUnavailable as exc:
            raise HTTPException(status_code=503, detail=f"legacy questionnaire production data unavailable: {exc}") from exc
    return ListQuestionnairesQuery()(limit=limit, offset=offset)


@router.get("/api/admin/questionnaires/preflight")
async def questionnaire_preflight(request: Request) -> dict | Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    return GetQuestionnairePreflightQuery()()


@router.post("/api/admin/questionnaires")
def create_questionnaire(payload: dict[str, Any]) -> dict:
    try:
        if production_data_ready():
            return create_questionnaire_in_legacy(payload)
        return UpsertQuestionnaireCommand()(QuestionnaireUpsertRequest.model_validate(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}")
def get_questionnaire(questionnaire_id: int) -> dict:
    try:
        if production_data_ready():
            return _questionnaire_payload_with_nested_questions(
                get_questionnaire_detail_from_legacy(questionnaire_id)
            )
        return GetQuestionnaireDetailQuery()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/questionnaires/{questionnaire_id}")
def update_questionnaire(questionnaire_id: int, payload: dict[str, Any]) -> dict:
    try:
        if production_data_ready():
            return update_questionnaire_in_legacy(questionnaire_id, payload)
        return UpsertQuestionnaireCommand()(QuestionnaireUpsertRequest.model_validate(payload), questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/questionnaires/{questionnaire_id}/disable")
def disable_questionnaire(questionnaire_id: int, payload: dict | None = None) -> dict:
    try:
        enabled = not bool((payload or {}).get("is_disabled", True))
        if production_data_ready():
            return set_questionnaire_enabled_in_legacy(questionnaire_id, enabled=enabled)
        return SetQuestionnaireEnabledCommand()(questionnaire_id, enabled=enabled)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/questionnaires/{questionnaire_id}/enable")
def enable_questionnaire(questionnaire_id: int) -> dict:
    try:
        if production_data_ready():
            return set_questionnaire_enabled_in_legacy(questionnaire_id, enabled=True)
        return SetQuestionnaireEnabledCommand()(questionnaire_id, enabled=True)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/questionnaires/{questionnaire_id}")
def delete_questionnaire(questionnaire_id: int) -> dict:
    try:
        if production_data_ready():
            return delete_questionnaire_in_legacy(questionnaire_id)
        return DeleteQuestionnaireCommand()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/export")
def export_questionnaire(questionnaire_id: int) -> Response:
    try:
        if production_data_ready():
            return _download_export_response(
                questionnaire_id,
                export_questionnaire_from_legacy(questionnaire_id),
            )
        return _download_export_response(questionnaire_id, ExportQuestionnaireQuery()(questionnaire_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug")
def latest_submit_debug(questionnaire_id: int) -> dict:
    try:
        if production_data_ready():
            return latest_submit_debug_from_legacy(questionnaire_id)
        return LatestSubmitDebugQuery()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/h5/questionnaires/{slug}")
def public_get_questionnaire(slug: str) -> dict:
    try:
        if production_data_ready():
            return _public_questionnaire_payload(get_public_questionnaire_from_legacy(slug))
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
        if production_data_ready():
            payload = _public_questionnaire_payload(get_public_questionnaire_from_legacy(slug))
        else:
            payload = GetPublicQuestionnaireQuery()(slug)
    except Exception as exc:
        _raise_http(exc)
    questionnaire = jsonable_encoder(payload["questionnaire"])
    questions = jsonable_encoder(payload.get("questions") or [])
    source_params = _request_values(request, _QUESTIONNAIRE_SOURCE_PARAM_FIELDS)
    request_hints = _request_values(request, _QUESTIONNAIRE_META_FIELDS)
    session_identity = legacy_questionnaire_session_identity(request.cookies)
    is_wechat_browser = _is_wechat_browser(request)
    is_authorized = bool(session_identity.get("openid"))
    oauth_configured = legacy_questionnaire_oauth_is_configured()
    page_mode = "auth_gate" if is_wechat_browser and not is_authorized else "questionnaire"
    env_notice = ""
    if page_mode == "auth_gate":
        env_notice = "授权后即可填写问卷信息。" if oauth_configured else "当前微信登录配置未完成，请联系管理员。"
    page_state = {
        "mode": page_mode,
        "slug": slug,
        "title": questionnaire["title"],
        "description": questionnaire.get("description") or "",
        "env_notice": env_notice,
        "oauth_start_url": _questionnaire_oauth_start_url(slug, source_params) if oauth_configured else "",
        "submit_url": f"/api/h5/questionnaires/{slug}/submit",
        "api_url": f"/api/h5/questionnaires/{slug}",
        "diagnostics_url": f"/api/h5/questionnaires/{slug}/client-diagnostics",
        "submitted_url": f"/s/{slug}/submitted",
        "request_hints": request_hints,
        "initial_questionnaire": {**questionnaire, "questions": questions} if page_mode == "questionnaire" else None,
        "answer_display_mode": questionnaire.get("answer_display_mode") or "all_in_one",
        "prefill_fields": {},
        "form_error": "",
        "is_wechat_browser": is_wechat_browser,
        "is_authorized": is_authorized,
    }
    return templates.TemplateResponse(
        request,
        "questionnaire_h5_page.html",
        {"request": request, "page_state": page_state},
    )


@router.get("/s/{slug}/submitted", response_class=HTMLResponse)
def public_questionnaire_submitted(request: Request, slug: str):
    return templates.TemplateResponse(request, "questionnaire_h5_submitted.html", {"request": request})
