from __future__ import annotations

import os
from typing import Any

from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.integration_gateway.questionnaire_adapters import (
    QuestionnaireSubmitSideEffectGateway,
    WeChatOAuthAdapter,
    build_wechat_oauth_adapter,
)
from aicrm_next.shared.errors import ContractError, NotFoundError

from .domain import admin_detail_projection, public_projection, score_and_tags, summary_projection, validate_required_answers
from .dto import OAuthCallbackRequest, OAuthStartRequest, QuestionnaireSubmitRequest, QuestionnaireUpsertRequest
from .repo import QuestionnaireRepository, build_questionnaire_repository


class ListQuestionnairesQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        rows, total = self._repo.list_questionnaires(limit=limit, offset=offset)
        items = [summary_projection(item) for item in rows]
        return {"ok": True, "items": items, "questionnaires": items, "total": total, "limit": limit, "offset": offset}

    __call__ = execute


class GetQuestionnaireDetailQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, questionnaire_id: int) -> dict[str, Any]:
        item = self._repo.get_questionnaire(questionnaire_id)
        if not item:
            raise NotFoundError("questionnaire not found")
        return {"ok": True, **admin_detail_projection(item)}

    __call__ = execute


class UpsertQuestionnaireCommand:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, payload: QuestionnaireUpsertRequest, questionnaire_id: int | None = None) -> dict[str, Any]:
        if not payload.title.strip():
            raise ContractError("title is required")
        saved = self._repo.save_questionnaire(payload.model_dump(), questionnaire_id)
        if not saved:
            raise NotFoundError("questionnaire not found")
        detail = admin_detail_projection(saved)
        return {"ok": True, **detail}

    __call__ = execute


class SetQuestionnaireEnabledCommand:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, questionnaire_id: int, *, enabled: bool) -> dict[str, Any]:
        item = self._repo.set_enabled(questionnaire_id, enabled)
        if not item:
            raise NotFoundError("questionnaire not found")
        return {"ok": True, "questionnaire": summary_projection(item)}

    __call__ = execute


class DeleteQuestionnaireCommand:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, questionnaire_id: int) -> dict[str, Any]:
        if not self._repo.get_questionnaire(questionnaire_id):
            raise NotFoundError("questionnaire not found")
        return {"ok": True, "deleted": self._repo.delete_questionnaire(questionnaire_id), "delete_mode": "hard_delete_fixture"}

    __call__ = execute


class ExportQuestionnaireQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, questionnaire_id: int) -> dict[str, Any]:
        export = self._repo.export_submissions(questionnaire_id)
        if export is None:
            raise NotFoundError("questionnaire not found")
        return {"ok": True, "export": export}

    __call__ = execute


def _normalized_share_url(value: str) -> str:
    return str(value or "").strip()


def _questionnaire_share_qr_data_url(share_url: str) -> str:
    from aicrm_next.shared.share_qr import svg_qr_data_url

    return svg_qr_data_url(_normalized_share_url(share_url), encoding="url")


def build_questionnaire_share_payload(questionnaire: dict[str, Any], *, share_url: str) -> dict[str, Any]:
    normalized = summary_projection(questionnaire)
    url = _normalized_share_url(share_url)
    if not url:
        raise ContractError("questionnaire share url is required")
    return {
        "questionnaire_id": normalized["id"],
        "slug": normalized["slug"],
        "title": normalized["title"] or normalized["name"],
        "url": url,
        "public_path": normalized["public_path"],
        "qr_data_url": _questionnaire_share_qr_data_url(url),
    }


class GetQuestionnaireShareQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, questionnaire_id: int, *, share_url: str) -> dict[str, Any]:
        item = self._repo.get_questionnaire(questionnaire_id)
        if not item:
            raise NotFoundError("questionnaire not found")
        return {"ok": True, "share": build_questionnaire_share_payload(item, share_url=share_url)}

    __call__ = execute


class GetQuestionnairePreflightQuery:
    def execute(self) -> dict[str, Any]:
        secret_key = os.getenv("SECRET_KEY", "").strip()
        wechat_oauth_configured = bool(
            os.getenv("WECHAT_MP_APP_ID", "").strip()
            and os.getenv("WECHAT_MP_APP_SECRET", "").strip()
            and secret_key
            and secret_key != "dev-secret-key-change-me"
        )
        wecom_contact_configured = bool(
            os.getenv("WECOM_CORP_ID", "").strip()
            and os.getenv("WECOM_CONTACT_SECRET", "").strip()
        )
        wecom_tags_api_available = bool(
            os.getenv("WECOM_CORP_ID", "").strip()
            and os.getenv("WECOM_SECRET", "").strip()
            and os.getenv("WECOM_API_BASE", "https://qyapi.weixin.qq.com").strip()
        )
        return {
            "ok": True,
            "checks": {
                "wechat_oauth_configured": wechat_oauth_configured,
                "wecom_contact_configured": wecom_contact_configured,
                "debug_session_api_enabled": True,
                "questionnaire_admin_ui_enabled": True,
                "wecom_tags_api_available": wecom_tags_api_available,
                "identity_map_available": True,
            },
            "status": (
                "ok"
                if wechat_oauth_configured and wecom_contact_configured and wecom_tags_api_available
                else "partial"
            ),
        }

    __call__ = execute


class LatestSubmitDebugQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, questionnaire_id: int) -> dict[str, Any]:
        if not self._repo.get_questionnaire(questionnaire_id):
            raise NotFoundError("questionnaire not found")
        latest = self._repo.latest_submission(questionnaire_id)
        return {"ok": True, "submission": latest, "source_status": "fixture", "safe_debug": True}

    __call__ = execute


class GetPublicQuestionnaireQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, slug: str) -> dict[str, Any]:
        item = self._repo.get_questionnaire_by_slug(slug)
        if not item:
            raise NotFoundError("questionnaire not found")
        if not bool(item.get("enabled", True)):
            raise NotFoundError("questionnaire disabled")
        return {"ok": True, **public_projection(item)}

    __call__ = execute


class SubmitQuestionnaireCommand:
    def __init__(
        self,
        repo: QuestionnaireRepository | None = None,
        identity_query: ResolvePersonIdentityQuery | None = None,
        side_effect_gateway: QuestionnaireSubmitSideEffectGateway | None = None,
    ) -> None:
        self._repo = repo or build_questionnaire_repository()
        self._identity_query = identity_query or ResolvePersonIdentityQuery()
        self._side_effect_gateway = side_effect_gateway or QuestionnaireSubmitSideEffectGateway()

    def execute(self, slug: str, payload: QuestionnaireSubmitRequest) -> dict[str, Any]:
        item = self._repo.get_questionnaire_by_slug(slug)
        if not item:
            raise NotFoundError("questionnaire not found")
        if not bool(item.get("enabled", True)):
            raise NotFoundError("questionnaire disabled")
        validate_required_answers(item, payload.answers)
        identity = self._identity_query(
            ResolvePersonIdentityRequest(
                mobile=payload.respondent_identity.get("mobile"),
                external_userid=payload.respondent_identity.get("external_userid"),
                openid=payload.respondent_identity.get("openid"),
                unionid=payload.respondent_identity.get("unionid"),
            )
        )
        score, final_tags = score_and_tags(item, payload.answers)
        submission = self._repo.create_submission(
            {
                "questionnaire_id": item["id"],
                "slug": item["slug"],
                "answers": dict(payload.answers),
                "respondent_identity": dict(payload.respondent_identity),
                "person_id": identity.person_id if identity else None,
                "external_userid": (identity.external_userid if identity else payload.respondent_identity.get("external_userid")) or "",
                "mobile": (identity.mobile if identity else payload.respondent_identity.get("mobile")) or "",
                "binding_status": identity.binding_status if identity else "unresolved",
                "score": score,
                "final_tags": final_tags,
            }
        )
        tag_result = self._side_effect_gateway.apply_tags(
            questionnaire_id=item["id"],
            submission_id=submission["submission_id"],
            external_userid=submission.get("external_userid") or "",
            tag_ids=final_tags,
        )
        external_push_config = item.get("external_push_config") if isinstance(item.get("external_push_config"), dict) else {}
        webhook_url = str(external_push_config.get("webhook_url") or "") if external_push_config.get("enabled") else ""
        push_result = self._side_effect_gateway.emit_external_push(
            questionnaire_id=item["id"],
            submission_id=submission["submission_id"],
            webhook_url=webhook_url,
            payload_summary={
                "slug": item["slug"],
                "score": score,
                "final_tag_count": len(final_tags),
                "external_userid": submission.get("external_userid") or "",
            },
        )
        automation_gateway_result = self._side_effect_gateway.emit_automation_questionnaire_result(
            questionnaire=item,
            submission=submission,
            final_tags=final_tags,
        )
        automation_event = self._automation_event_from_gateway(automation_gateway_result)
        return {
            "ok": True,
            "submission_id": submission["submission_id"],
            "questionnaire_id": item["id"],
            "slug": item["slug"],
            "external_userid": submission.get("external_userid") or "",
            "person_id": submission.get("person_id"),
            "mobile": submission.get("mobile") or "",
            "binding_status": submission.get("binding_status") or "unresolved",
            "score": score,
            "final_tags": final_tags,
            "redirect_url": item.get("redirect_url") or f"/s/{item['slug']}/submitted",
            "result_message": "提交成功",
            "automation_event": automation_event,
            "side_effect_safety": self._side_effect_gateway.side_effect_safety(),
            "side_effects": {
                "wecom_tag": tag_result,
                "external_push": push_result,
                "automation": automation_gateway_result,
            },
        }

    __call__ = execute

    def _automation_event_from_gateway(self, gateway_result: dict[str, Any]) -> dict[str, Any]:
        result = gateway_result.get("result") if isinstance(gateway_result.get("result"), dict) else {}
        return {
            "ok": True,
            "source_status": result.get("source_status", "fixture_boundary"),
            "member_id": result.get("member_id", ""),
            "followup_type": result.get("followup_type", "normal"),
            "current_pool": result.get("current_pool", ""),
        }


class GetSubmissionResultQuery:
    def __init__(self, repo: QuestionnaireRepository | None = None) -> None:
        self._repo = repo or build_questionnaire_repository()

    def execute(self, slug: str, submission_id: str) -> dict[str, Any]:
        item = self._repo.get_questionnaire_by_slug(slug)
        if not item:
            raise NotFoundError("questionnaire not found")
        submission = self._repo.get_submission(submission_id)
        if not submission or submission.get("slug") != slug:
            raise NotFoundError("submission not found")
        return {"ok": True, "result": submission, "result_message": "提交成功"}

    __call__ = execute


class StartWechatOAuthQuery:
    def __init__(self, adapter: WeChatOAuthAdapter | None = None) -> None:
        self._adapter = adapter or build_wechat_oauth_adapter()

    def execute(self, request: OAuthStartRequest) -> dict[str, Any]:
        adapter_result = self._adapter.build_authorize_url(
            slug=request.slug,
            state=request.state,
            redirect=request.redirect,
            openid=request.openid,
            unionid=request.unionid,
            external_userid=request.external_userid,
        )
        result = adapter_result.get("result") if isinstance(adapter_result.get("result"), dict) else {}
        return {
            "ok": bool(adapter_result.get("ok")),
            "redirect_url": result.get("redirect_url", ""),
            "state": result.get("state", request.state or request.slug or ""),
            "source_status": result.get("source_status", "fake" if adapter_result.get("ok") else "adapter_error"),
            "oauth_provider": result.get("oauth_provider", "wechat_mp"),
        }

    __call__ = execute


class CompleteWechatOAuthCallbackCommand:
    def __init__(self, adapter: WeChatOAuthAdapter | None = None) -> None:
        self._adapter = adapter or build_wechat_oauth_adapter()

    def execute(self, request: OAuthCallbackRequest) -> dict[str, Any]:
        adapter_result = self._adapter.resolve_oauth_identity(
            state=request.state,
            redirect=request.redirect,
            openid=request.openid,
            unionid=request.unionid,
            external_userid=request.external_userid,
        )
        result = adapter_result.get("result") if isinstance(adapter_result.get("result"), dict) else {}
        return {
            "ok": bool(adapter_result.get("ok")),
            "openid": result.get("openid", request.openid or "openid_fake_001"),
            "unionid": result.get("unionid", request.unionid or "unionid_fake_001"),
            "external_userid": result.get("external_userid", request.external_userid or ""),
            "redirect_url": result.get("redirect_url", request.redirect or (f"/s/{request.state}" if request.state else "/")),
            "state": result.get("state", request.state or ""),
            "source_status": result.get("source_status", "fake" if request.state else "missing_config"),
        }

    __call__ = execute
