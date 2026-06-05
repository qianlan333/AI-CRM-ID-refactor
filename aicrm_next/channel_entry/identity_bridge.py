from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from .domain import ENTRY_CHANGE_TYPES, text
from .wecom_adapter import WeComAdapterBlocked, WeComApiError, get_wecom_adapter

SIDEBAR_IDENTITY_REFRESH_INTERVAL_SECONDS = 60


@lru_cache(maxsize=1)
def _legacy_app():
    from wecom_ability_service import create_app

    return create_app()


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


def _preferred_owner_userid(owner_userid: str, detail: dict[str, Any]) -> str:
    owner = text(owner_userid)
    if owner:
        return owner
    for item in list((detail or {}).get("follow_user") or []):
        userid = text((item or {}).get("userid"))
        if userid:
            return userid
    return ""


def _age_seconds(value: Any) -> int | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.utcnow()
    return max(0, int((now - value).total_seconds()))


def _identity_bridge_state(external_userid: str) -> dict[str, Any]:
    with _legacy_app().app_context():
        from wecom_ability_service.db import get_db

        row = get_db().execute(
            """
            SELECT im.external_userid,
                   COALESCE(im.unionid, '') AS unionid,
                   COALESCE(im.openid, '') AS openid,
                   im.updated_at,
                   CASE WHEN b.external_userid IS NULL THEN FALSE ELSE TRUE END AS mobile_bound
            FROM wecom_external_contact_identity_map im
            LEFT JOIN external_contact_bindings b
              ON b.external_userid = im.external_userid
            WHERE im.external_userid = ?
            ORDER BY im.updated_at DESC, im.id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()
    if not row:
        return {"exists": False, "reason": "identity_missing"}
    payload = dict(row)
    payload["exists"] = True
    payload["unionid_present"] = bool(text(payload.get("unionid")))
    payload["openid_present"] = bool(text(payload.get("openid")))
    payload["mobile_bound"] = bool(payload.get("mobile_bound"))
    payload["age_seconds"] = _age_seconds(payload.get("updated_at"))
    return payload


def _refresh_reason(state: dict[str, Any], *, min_interval_seconds: int) -> str:
    if not state.get("exists"):
        return "identity_missing"
    age = state.get("age_seconds")
    if isinstance(age, int) and age < min_interval_seconds:
        return ""
    if not state.get("unionid_present") and not state.get("openid_present"):
        return "identity_missing_unionid_openid"
    if not state.get("mobile_bound"):
        return "mobile_not_bound"
    return ""


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
        owner_userid = _preferred_owner_userid(owner_userid, dict(detail or {}))

        legacy_app = _legacy_app()
        with legacy_app.app_context():
            effective_corp_id = text(corp_id) or text(legacy_app.config.get("WECOM_CORP_ID"))
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
                corp_id=effective_corp_id,
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
                    corp_id=effective_corp_id,
                    external_userid=external_userid,
                    follow_users=list((detail or {}).get("follow_user") or []),
                    preferred_userid=owner_userid,
                )
            )
            RefreshExternalContactIdentityOwnerCommand()(
                RefreshExternalContactIdentityOwnerCommandDTO(corp_id=effective_corp_id, external_userid=external_userid)
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


def ensure_external_contact_identity_for_sidebar(
    *,
    external_userid: str,
    owner_userid: str = "",
    corp_id: str = "",
    min_interval_seconds: int = SIDEBAR_IDENTITY_REFRESH_INTERVAL_SECONDS,
) -> dict[str, Any]:
    normalized_external_userid = text(external_userid)
    if not normalized_external_userid:
        return {"status": "skipped", "reason": "external_userid_missing"}
    state = _identity_bridge_state(normalized_external_userid)
    reason = _refresh_reason(state, min_interval_seconds=max(0, int(min_interval_seconds)))
    if not reason:
        return {
            "status": "skipped",
            "reason": "identity_fresh",
            "unionid_present": bool(state.get("unionid_present")),
            "openid_present": bool(state.get("openid_present")),
            "mobile_bound": bool(state.get("mobile_bound")),
            "age_seconds": state.get("age_seconds"),
        }
    result = sync_external_contact_identity_for_event(
        {
            "Event": "change_external_contact",
            "ChangeType": "edit_external_contact",
            "ExternalUserID": normalized_external_userid,
            "UserID": text(owner_userid),
        },
        corp_id=text(corp_id),
    )
    mobile_binding = dict((result or {}).get("mobile_binding") or {})
    questionnaire_backfill = dict((result or {}).get("questionnaire_backfill") or {})
    return {
        "status": "attempted",
        "reason": reason,
        "sync_status": text((result or {}).get("status")),
        "sync_reason": text((result or {}).get("reason")),
        "unionid_present": bool((result or {}).get("unionid_present")),
        "openid_present": bool((result or {}).get("openid_present")),
        "mobile_binding_status": text(mobile_binding.get("status")),
        "mobile_bound": text(mobile_binding.get("status")) in {"bound", "already_bound"},
        "questionnaire_updated_count": int(questionnaire_backfill.get("updated_count") or 0),
    }
