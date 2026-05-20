from __future__ import annotations

from typing import Any

from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.shared.errors import ContractError, NotFoundError

from .domain import admin_detail_projection, public_projection, score_and_tags, summary_projection, validate_required_answers
from .dto import OAuthCallbackRequest, OAuthStartRequest, QuestionnaireSubmitRequest, QuestionnaireUpsertRequest
from .oauth import FakeWechatOAuthAdapter
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


class GetQuestionnairePreflightQuery:
    def execute(self) -> dict[str, Any]:
        return {
            "ok": True,
            "checks": {
                "wechat_oauth_configured": False,
                "wecom_contact_configured": False,
                "debug_session_api_enabled": True,
                "questionnaire_admin_ui_enabled": True,
                "wecom_tags_api_available": False,
                "identity_map_available": True,
            },
            "status": "partial",
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
    ) -> None:
        self._repo = repo or build_questionnaire_repository()
        self._identity_query = identity_query or ResolvePersonIdentityQuery()

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
        automation_event = self._emit_automation_event(item, submission, final_tags)
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
        }

    __call__ = execute

    def _emit_automation_event(self, item: dict[str, Any], submission: dict[str, Any], final_tags: list[str]) -> dict[str, Any]:
        from aicrm_next.automation_engine.application import ApplyQuestionnaireResultCommand
        from aicrm_next.automation_engine.dto import ApplyQuestionnaireResultRequest

        followup_type = "priority" if "tag_interest_ai_tools" in final_tags else "normal"
        result = ApplyQuestionnaireResultCommand()(
            ApplyQuestionnaireResultRequest(
                person_id=submission.get("person_id"),
                external_userid=submission.get("external_userid"),
                mobile=submission.get("mobile"),
                customer_name="问卷提交用户",
                followup_type=followup_type,
                questionnaire_id=item.get("id"),
                submission_id=submission.get("submission_id"),
                final_tags=final_tags,
                source="questionnaire_submit_pipeline",
                operator="system",
                reason="questionnaire_submit_boundary",
            )
        )
        return {
            "ok": True,
            "source_status": result.get("source_status", "fixture_boundary"),
            "member_id": result.get("member", {}).get("member_id", ""),
            "followup_type": followup_type,
            "current_pool": result.get("member", {}).get("current_pool", ""),
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
    def __init__(self, adapter: FakeWechatOAuthAdapter | None = None) -> None:
        self._adapter = adapter or FakeWechatOAuthAdapter()

    def execute(self, request: OAuthStartRequest) -> dict[str, Any]:
        return self._adapter.start(request)

    __call__ = execute


class CompleteWechatOAuthCallbackCommand:
    def __init__(self, adapter: FakeWechatOAuthAdapter | None = None) -> None:
        self._adapter = adapter or FakeWechatOAuthAdapter()

    def execute(self, request: OAuthCallbackRequest) -> dict[str, Any]:
        return self._adapter.callback(request)

    __call__ = execute
