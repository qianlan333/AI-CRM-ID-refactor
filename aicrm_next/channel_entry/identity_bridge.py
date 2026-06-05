from __future__ import annotations

from typing import Any

from .domain import ENTRY_CHANGE_TYPES, text
from .wecom_adapter import WeComAdapterBlocked, WeComApiError, get_wecom_adapter


def _adapter_failure(exc: Exception) -> tuple[str, dict[str, Any]]:
    if isinstance(exc, WeComAdapterBlocked):
        payload: dict[str, Any] = {"reason": exc.reason}
        if exc.missing_config:
            payload["missing_config"] = exc.missing_config
        return exc.reason, payload
    if isinstance(exc, WeComApiError):
        payload = {"reason": "wecom_api_error", "message": exc.message}
        if exc.payload:
            payload["wecom_result"] = exc.payload
        return "wecom_api_error", payload
    return "wecom_api_error", {"reason": "wecom_api_error", "message": str(exc)}


def sync_external_contact_identity_for_event(event: dict[str, Any], *, corp_id: str) -> dict[str, Any]:
    if text(event.get("Event")) != "change_external_contact" or text(event.get("ChangeType")) not in ENTRY_CHANGE_TYPES:
        return {"status": "skipped", "reason": "unsupported_event"}
    external_userid = text(event.get("ExternalUserID"))
    owner_userid = text(event.get("UserID"))
    if not external_userid:
        return {"status": "skipped", "reason": "external_userid_missing"}

    try:
        adapter = get_wecom_adapter()
        detail_loader = getattr(adapter, "get_external_contact_detail", None)
        if not callable(detail_loader):
            return {"status": "skipped", "reason": "adapter_missing_get_external_contact_detail"}
        detail = detail_loader(external_userid)
        if int((detail or {}).get("errcode") or 0) != 0:
            return {"status": "failed", "reason": "wecom_api_error", "wecom_result": dict(detail or {})}

        from wecom_ability_service.application.identity_contact.commands import (
            BindExternalContactMobileFromIdentitySourcesCommand,
            BuildExternalContactIdentityRecordCommand,
            RefreshExternalContactIdentityOwnerCommand,
            ReplaceFollowUsersCommand,
            UpsertExternalContactIdentityCommand,
        )
        from wecom_ability_service.application.identity_contact.dto import (
            BindExternalContactMobileFromIdentitySourcesCommandDTO,
            RefreshExternalContactIdentityOwnerCommandDTO,
            ReplaceFollowUsersCommandDTO,
            UpsertExternalContactIdentityCommandDTO,
        )

        record = BuildExternalContactIdentityRecordCommand()(
            corp_id=text(corp_id),
            detail=dict(detail or {}),
            follow_user_userid=owner_userid,
            status="active",
        )
        if not text(record.get("external_userid")):
            return {"status": "skipped", "reason": "contact_detail_missing_external_userid"}

        identity_map_id = UpsertExternalContactIdentityCommand()(
            UpsertExternalContactIdentityCommandDTO(record=record)
        )
        ReplaceFollowUsersCommand()(
            ReplaceFollowUsersCommandDTO(
                corp_id=text(corp_id),
                external_userid=external_userid,
                follow_users=list((detail or {}).get("follow_user") or []),
                preferred_userid=owner_userid,
            )
        )
        RefreshExternalContactIdentityOwnerCommand()(
            RefreshExternalContactIdentityOwnerCommandDTO(corp_id=text(corp_id), external_userid=external_userid)
        )
        mobile_binding = BindExternalContactMobileFromIdentitySourcesCommand()(
            BindExternalContactMobileFromIdentitySourcesCommandDTO(
                external_userid=external_userid,
                owner_userid=owner_userid,
                bind_by_userid=owner_userid or "wecom_external_contact_callback",
            )
        )
        questionnaire_backfill: dict[str, Any] = {"status": "skipped", "reason": "mobile_not_bound"}
        if text((mobile_binding or {}).get("mobile")) and text((mobile_binding or {}).get("status")) in {"bound", "already_bound"}:
            from wecom_ability_service.domains.questionnaire.service import (
                backfill_questionnaire_submissions_for_mobile_binding,
            )

            questionnaire_backfill = backfill_questionnaire_submissions_for_mobile_binding(
                external_userid=external_userid,
                mobile=text(mobile_binding.get("mobile")),
                follow_user_userid=owner_userid,
            )
        return {
            "status": "success",
            "identity_map_id": int(identity_map_id or 0),
            "unionid_present": bool(text(record.get("unionid"))),
            "openid_present": bool(text(record.get("openid"))),
            "mobile_binding": mobile_binding,
            "questionnaire_backfill": questionnaire_backfill,
        }
    except Exception as exc:
        reason, failure = _adapter_failure(exc)
        return {"status": "failed", "reason": reason, **failure}
