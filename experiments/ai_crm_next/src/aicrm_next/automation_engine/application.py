from __future__ import annotations

from typing import Any

from aicrm_next.customer_read_model.application import GetCustomerChatContextQuery
from aicrm_next.customer_read_model.dto import CustomerChatContextRequest
from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.shared.errors import ContractError, NotFoundError

from .domain import execution_record_projection, overview_cards, pool_summary
from .dto import (
    ActivationWebhookRequest,
    ApplyActivationFactRequest,
    ApplyQuestionnaireResultRequest,
    ApplyTrialOpenedFactRequest,
    AutomationActionRequest,
    OverrideFollowupTypeRequest,
    PushOpenClawContextRequest,
)
from .repo import AutomationRepository, build_automation_repository
from .state_machine import apply_transition, normalize_followup_type
from .workflow import default_workflow_registry


def _filters_snapshot(**filters: Any) -> dict[str, str]:
    return {key: str(value or "") for key, value in filters.items()}


class GetAutomationRuntimeContractQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self) -> dict[str, Any]:
        return {"ok": True, "pools": self._repo.list_pools(), "workflows": default_workflow_registry(), "status": "partial"}

    __call__ = execute


class GetAutomationOverviewQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self) -> dict[str, Any]:
        members, total = self._repo.list_members(limit=500, offset=0)
        return {
            "ok": True,
            "cards": overview_cards(members),
            "total": total,
            "filters": {},
            "generated_at": "fixture",
            "status": "partial",
        }

    __call__ = execute


class ListAutomationPoolsQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self) -> dict[str, Any]:
        members, _ = self._repo.list_members(limit=500, offset=0)
        return {"ok": True, "pools": pool_summary(members), "total": len(self._repo.list_pools()), "generated_at": "fixture"}

    __call__ = execute


class ListAutomationMembersQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(
        self,
        *,
        current_pool: str = "",
        followup_type: str = "",
        owner_userid: str = "",
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        filters = _filters_snapshot(current_pool=current_pool, followup_type=followup_type, owner_userid=owner_userid, keyword=keyword)
        rows, total = self._repo.list_members(
            {"current_pool": current_pool, "followup_type": followup_type, "owner_userid": owner_userid, "keyword": keyword},
            limit=limit,
            offset=offset,
        )
        return {"ok": True, "items": rows, "total": total, "limit": limit, "offset": offset, "filters": filters}

    __call__ = execute


class GetAutomationMemberDetailQuery:
    def __init__(
        self,
        repo: AutomationRepository | None = None,
        customer_context_query: GetCustomerChatContextQuery | None = None,
    ) -> None:
        self._repo = repo or build_automation_repository()
        self._customer_context_query = customer_context_query or GetCustomerChatContextQuery()

    def execute(self, member_id: str) -> dict[str, Any]:
        member = self._repo.get_member(member_id)
        if not member:
            raise NotFoundError("automation member not found")
        customer_context = {}
        recent_timeline_events: list[dict[str, Any]] = []
        warnings = list(member.get("warnings") or [])
        external_userid = str(member.get("external_userid") or "")
        if external_userid:
            try:
                context = self._customer_context_query(
                    CustomerChatContextRequest(external_userid=external_userid, timeline_limit=5, recent_message_limit=5)
                )
                customer_context = context.get("customer") or {}
                recent_timeline_events = context.get("recent_timeline_events") or []
            except Exception:
                warnings.append("customer_context_unavailable")
        return {
            "ok": True,
            "member": member,
            "history": self._repo.list_history(member_id),
            "customer_context": customer_context,
            "recent_timeline_events": recent_timeline_events,
            "warnings": warnings,
        }

    __call__ = execute


class ApplyQuestionnaireResultCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, request: ApplyQuestionnaireResultRequest) -> dict[str, Any]:
        followup_type = normalize_followup_type(request.followup_type)
        member = self._repo.find_member(
            external_userid=request.external_userid,
            mobile=request.mobile,
            person_id=request.person_id,
        )
        is_new_member = False
        if not member:
            create_member = getattr(self._repo, "create_member_from_questionnaire", None)
            if not create_member:
                raise NotFoundError("automation member not found")
            member = create_member(request.model_dump())
            is_new_member = True
        if not is_new_member and self._should_ignore_questionnaire_reroute(member):
            updated, history = apply_transition(
                member,
                trigger="questionnaire_result_ignored",
                source=request.source,
                operator=request.operator,
                reason="questionnaire_result_received_after_initial_split",
                patch={
                    "last_ignored_questionnaire_result": {
                        "incoming_followup_type": followup_type,
                        "questionnaire_id": request.questionnaire_id,
                        "submission_id": request.submission_id,
                        "final_tags": request.final_tags,
                    }
                },
            )
            self._repo.save_member(updated)
            self._repo.create_execution_record(
                {
                    "record_type": "questionnaire_event",
                    "member_id": updated["member_id"],
                    "trigger": "questionnaire_result_ignored",
                    "status": "succeeded",
                    "status_label": "已记录问卷结果，未重新分流",
                    "payload_preview": {
                        "incoming_followup_type": followup_type,
                        "effective_followup_type": updated["followup_type"],
                        "after_pool": updated["current_pool"],
                    },
                }
            )
            return {"ok": True, "member": updated, "history": history, "source_status": "fixture_boundary", "rerouted": False}
        updated, history = apply_transition(
            member,
            trigger="questionnaire_result",
            source=request.source,
            operator=request.operator,
            reason=request.reason,
            patch={
                "questionnaire_followup_type": followup_type,
                "followup_type": followup_type,
                "last_questionnaire_id": request.questionnaire_id,
                "last_submission_id": request.submission_id,
                "last_final_tags": request.final_tags,
            },
        )
        self._repo.save_member(updated)
        self._repo.create_execution_record(
            {
                "record_type": "questionnaire_event",
                "member_id": updated["member_id"],
                "trigger": "questionnaire_result",
                "status": "succeeded",
                "status_label": "已记录问卷分流",
                "payload_preview": {"followup_type": followup_type, "after_pool": updated["current_pool"]},
            }
        )
        return {"ok": True, "member": updated, "history": history, "source_status": "fixture_boundary"}

    __call__ = execute

    def _should_ignore_questionnaire_reroute(self, member: dict[str, Any]) -> bool:
        has_questionnaire_split = bool(str(member.get("questionnaire_followup_type") or "").strip())
        has_manual_override = bool(str(member.get("manual_followup_type") or "").strip())
        already_left_initial_pool = str(member.get("current_pool") or "new_user") != "new_user"
        return has_questionnaire_split or has_manual_override or already_left_initial_pool


class ApplyTrialOpenedFactCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, request: ApplyTrialOpenedFactRequest) -> dict[str, Any]:
        member = self._repo.get_member(request.member_id)
        if not member:
            raise NotFoundError("automation member not found")
        updated, history = apply_transition(
            member,
            trigger="trial_opened",
            source=request.source,
            operator=request.operator,
            reason=request.reason,
            occurred_at=request.occurred_at,
            patch={"trial_opened": True},
        )
        self._repo.save_member(updated)
        return {"ok": True, "member": updated, "history": history}

    __call__ = execute


class ApplyActivationFactCommand:
    def __init__(
        self,
        repo: AutomationRepository | None = None,
        identity_query: ResolvePersonIdentityQuery | None = None,
    ) -> None:
        self._repo = repo or build_automation_repository()
        self._identity_query = identity_query or ResolvePersonIdentityQuery()

    def execute(self, request: ApplyActivationFactRequest) -> dict[str, Any]:
        member = self._resolve_member(member_id=request.member_id, external_userid=request.external_userid, mobile=request.mobile)
        previous_pool = member["current_pool"]
        updated, history = apply_transition(
            member,
            trigger="activation_fact",
            source=request.source,
            operator=request.operator,
            reason=request.reason,
            occurred_at=request.activated_at,
            patch={"activated": True, "trial_opened": True},
        )
        self._repo.save_member(updated)
        self._repo.create_execution_record(
            {
                "record_type": "activation_webhook",
                "member_id": updated["member_id"],
                "trigger": "activation_fact",
                "status": "succeeded",
                "status_label": "已记录激活",
                "payload_preview": {"previous_pool": previous_pool, "current_pool": updated["current_pool"]},
            }
        )
        return {"ok": True, "member": updated, "previous_pool": previous_pool, "current_pool": updated["current_pool"], "history": history, "warnings": []}

    def _resolve_member(self, *, member_id: str | None, external_userid: str | None, mobile: str | None) -> dict[str, Any]:
        if member_id:
            member = self._repo.get_member(member_id)
            if member:
                return member
        if external_userid or mobile:
            identity = self._identity_query(ResolvePersonIdentityRequest(external_userid=external_userid, mobile=mobile))
            member = self._repo.find_member(
                external_userid=external_userid or (identity.external_userid if identity else None),
                mobile=mobile or (identity.mobile if identity else None),
                person_id=identity.person_id if identity else None,
            )
            if member:
                return member
        raise NotFoundError("automation member not found")

    __call__ = execute


class OverrideFollowupTypeCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, member_id: str, request: OverrideFollowupTypeRequest) -> dict[str, Any]:
        member = self._repo.get_member(member_id)
        if not member:
            raise NotFoundError("automation member not found")
        followup_type = normalize_followup_type(request.followup_type)
        updated, history = apply_transition(
            member,
            trigger="manual_override",
            source="admin",
            operator=request.operator,
            reason=request.reason,
            patch={"manual_followup_type": followup_type, "followup_type": followup_type},
        )
        self._repo.save_member(updated)
        return {"ok": True, "member": updated, "history": history}

    __call__ = execute


class ConfirmConversionCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        return self._action(member_id, request, trigger="confirm_conversion")

    def _action(self, member_id: str, request: AutomationActionRequest, *, trigger: str) -> dict[str, Any]:
        member = self._repo.get_member(member_id)
        if not member:
            raise NotFoundError("automation member not found")
        updated, history = apply_transition(member, trigger=trigger, source="admin", operator=request.operator, reason=request.reason)
        self._repo.save_member(updated)
        return {"ok": True, "member": updated, "history": history}

    __call__ = execute


class EnterSilentPoolCommand(ConfirmConversionCommand):
    def execute(self, member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        return self._action(member_id, request, trigger="enter_silent")

    __call__ = execute


class ExitMarketingCommand(ConfirmConversionCommand):
    def execute(self, member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        return self._action(member_id, request, trigger="exit_marketing")

    __call__ = execute


class PushMemberContextToOpenClawCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, member_id: str, request: PushOpenClawContextRequest) -> dict[str, Any]:
        detail = GetAutomationMemberDetailQuery(self._repo)(member_id)
        payload_preview = {
            "member_id": member_id,
            "customer_context": detail.get("customer_context") or {},
            "questionnaire_summary": {
                "questionnaire_followup_type": detail["member"].get("questionnaire_followup_type"),
                "manual_followup_type": detail["member"].get("manual_followup_type"),
            },
            "current_pool": detail["member"].get("current_pool"),
            "recent_timeline_events": detail.get("recent_timeline_events") or [],
        }
        record = self._repo.create_execution_record(
            {
                "record_type": "openclaw_push",
                "member_id": member_id,
                "trigger": "push_openclaw_context",
                "status": "succeeded",
                "status_label": "Fake 推送已记录",
                "delivery_status": "fake",
                "payload_preview": payload_preview,
            }
        )
        return {"ok": True, "delivery_status": "fake", "payload_preview": payload_preview, "warnings": ["openclaw_not_called"], "record": record}

    __call__ = execute


class ListAutomationExecutionRecordsQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        rows, total = self._repo.list_execution_records(limit=limit, offset=offset)
        return {"ok": True, "items": [execution_record_projection(item) for item in rows], "total": total, "limit": limit, "offset": offset}

    __call__ = execute


class ApplyActivationWebhookCommand:
    def execute(self, request: ActivationWebhookRequest) -> dict[str, Any]:
        if not (request.mobile or request.external_userid):
            raise ContractError("mobile or external_userid is required")
        return ApplyActivationFactCommand()(
            ApplyActivationFactRequest(
                mobile=request.mobile,
                external_userid=request.external_userid,
                activated_at=request.activated_at,
                source=request.source,
                operator=request.operator,
                reason="activation_webhook",
            )
        )

    __call__ = execute
