from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from fastapi.responses import JSONResponse

from aicrm_next.integration_gateway.legacy_flask_facade import _legacy_app

JsonDict = dict[str, Any]

_DEFAULT_TIMEZONE = "Asia/Shanghai"
_TOKEN_KEYS = ("AICRM_EXTERNAL_CAMPAIGN_TOKEN", "AUTOMATION_INTERNAL_API_TOKEN")
_ONE_RECIPIENT_SEGMENT_SQL = """
SELECT member_id, external_contact_id
FROM (
    SELECT (900000000000 + 2147483648 + hashtext(external_userid)::bigint) AS member_id,
           external_userid AS external_contact_id,
           0 AS source_rank
    FROM user_ops_pool_current
    WHERE external_userid = %(external_userid)s
    UNION ALL
    SELECT (900000000000 + 2147483648 + hashtext(external_contact_id)::bigint) AS member_id,
           external_contact_id,
           1 AS source_rank
    FROM automation_member
    WHERE external_contact_id = %(external_userid)s
      AND NOT EXISTS (
          SELECT 1 FROM user_ops_pool_current WHERE external_userid = %(external_userid)s
      )
) matched
ORDER BY source_rank ASC, member_id DESC
LIMIT 1
"""


class ExternalCampaignError(Exception):
    def __init__(self, error: str, *, status_code: int = 400) -> None:
        super().__init__(error)
        self.error = error
        self.status_code = status_code


def _text(value: object) -> str:
    return str(value or "").strip()


def _truthy(value: object) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _bool_value(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _slug(value: object, *, fallback: str = "external_campaign") -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def _hash_payload(*parts: object) -> str:
    joined = "\n".join(_text(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _configured_tokens() -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for key in _TOKEN_KEYS:
        token = _text(os.getenv(key))
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _provided_token(headers: Mapping[str, Any]) -> str:
    auth_header = _text(headers.get("authorization") or headers.get("Authorization"))
    if auth_header.startswith("Bearer "):
        return _text(auth_header[7:])
    return _text(headers.get("x-internal-api-token") or headers.get("X-Internal-Api-Token"))


def _auth_failure(headers: Mapping[str, Any]) -> tuple[str, int] | None:
    expected = _configured_tokens()
    if not expected:
        return ("external_campaign_token_not_configured", 503)
    provided = _provided_token(headers)
    if not provided:
        return ("missing_internal_token", 401)
    if provided not in expected:
        return ("invalid_internal_token", 401)
    return None


def _parse_local_datetime(value: object, *, default_timezone: str) -> datetime:
    raw = _text(value)
    if not raw:
        raise ExternalCampaignError("scheduled_for is required")
    normalized = raw.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExternalCampaignError("scheduled_for must be ISO datetime or YYYY-MM-DD HH:MM") from exc
    tz = ZoneInfo(default_timezone or _DEFAULT_TIMEZONE)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _first_schedule(payload: JsonDict, steps: list[JsonDict], *, timezone_name: str) -> datetime:
    for key in ("scheduled_for", "scheduled_at", "send_at"):
        if _text(payload.get(key)):
            return _parse_local_datetime(payload.get(key), default_timezone=timezone_name)
    first = steps[0] if steps else {}
    for key in ("scheduled_for", "scheduled_at", "send_at"):
        if _text(first.get(key)):
            return _parse_local_datetime(first.get(key), default_timezone=timezone_name)
    raise ExternalCampaignError("scheduled_for is required")


def _normalize_step_list(raw_steps: Any, payload: JsonDict, recipient: JsonDict, *, timezone_name: str) -> list[JsonDict]:
    source_steps = raw_steps if isinstance(raw_steps, list) and raw_steps else None
    if source_steps is None:
        content = (
            _text(recipient.get("content_text"))
            or _text(recipient.get("message"))
            or _text(payload.get("content_text"))
            or _text(payload.get("message"))
        )
        if not content:
            raise ExternalCampaignError("message/content_text is required")
        source_steps = [{"content_text": content}]

    first_dt = _first_schedule(payload, list(source_steps), timezone_name=timezone_name)
    anchor_date = first_dt.date()
    normalized: list[JsonDict] = []
    for index, item in enumerate(source_steps):
        if not isinstance(item, dict):
            raise ExternalCampaignError("steps items must be objects")
        content = _text(item.get("content_text")) or _text(item.get("message"))
        if not content:
            content = _text(recipient.get("content_text")) or _text(recipient.get("message"))
        if not content:
            raise ExternalCampaignError(f"steps[{index}].content_text is required")

        scheduled_value = item.get("scheduled_for") or item.get("scheduled_at") or item.get("send_at")
        if _text(scheduled_value):
            scheduled_dt = _parse_local_datetime(scheduled_value, default_timezone=timezone_name)
            day_offset = (scheduled_dt.date() - anchor_date).days
            send_time = scheduled_dt.strftime("%H:%M")
        else:
            day_offset = int(item.get("day_offset") if item.get("day_offset") is not None else index)
            send_time = _text(item.get("send_time")) or (first_dt.strftime("%H:%M") if index == 0 else "10:30")
        if day_offset < 0:
            raise ExternalCampaignError("step scheduled_for cannot be earlier than the first scheduled_for")
        if not re.match(r"^\d{2}:\d{2}$", send_time):
            raise ExternalCampaignError(f"steps[{index}].send_time must be HH:MM")
        hour, minute = [int(part) for part in send_time.split(":", 1)]
        scheduled_dt = datetime.combine(
            anchor_date + timedelta(days=day_offset),
            time(hour=hour, minute=minute),
            tzinfo=ZoneInfo(_text(item.get("timezone")) or timezone_name),
        )
        normalized.append(
            {
                "step_index": index,
                "day_offset": day_offset,
                "send_time": send_time,
                "timezone": _text(item.get("timezone")) or timezone_name,
                "scheduled_for": scheduled_dt.isoformat(),
                "content_text": content,
                "content_payload": item.get("content_payload") if isinstance(item.get("content_payload"), dict) else {},
                "stop_on_reply": _bool_value(
                    item.get("stop_on_reply", payload.get("stop_on_reply")),
                    default=True,
                ),
                "skip_if_recently_touched_days": int(
                    item.get("skip_if_recently_touched_days")
                    if item.get("skip_if_recently_touched_days") is not None
                    else payload.get("skip_if_recently_touched_days") or 0
                ),
            }
        )
    return normalized


def _normalize_recipients(payload: JsonDict) -> list[JsonDict]:
    raw_recipients = payload.get("recipients")
    recipients: list[JsonDict] = []
    if isinstance(raw_recipients, list) and raw_recipients:
        for item in raw_recipients:
            if isinstance(item, str):
                recipients.append({"external_userid": _text(item)})
            elif isinstance(item, dict):
                recipients.append(dict(item))
            else:
                raise ExternalCampaignError("recipients items must be strings or objects")
    else:
        external_userids = payload.get("external_userids")
        if isinstance(external_userids, list):
            recipients = [{"external_userid": _text(item)} for item in external_userids]
        elif _text(payload.get("external_userid")):
            recipients = [{"external_userid": _text(payload.get("external_userid"))}]
    cleaned = []
    seen = set()
    for item in recipients:
        external_userid = _text(item.get("external_userid") or item.get("external_contact_id"))
        if not external_userid:
            continue
        key = external_userid
        if key in seen:
            continue
        seen.add(key)
        item["external_userid"] = external_userid
        cleaned.append(item)
    if not cleaned:
        raise ExternalCampaignError("external_userid/external_userids/recipients is required")
    return cleaned


def _lookup_target(*, external_userid: str, owner_userid: str, strict_owner_match: bool) -> JsonDict:
    from wecom_ability_service.db import get_db

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, external_contact_id
        FROM automation_member
        WHERE external_contact_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (external_userid,),
    )
    member = cur.fetchone()
    if not member:
        raise ExternalCampaignError(f"automation_member_not_found:{external_userid}", status_code=404)

    contact: JsonDict = {}
    try:
        cur.execute(
            """
            SELECT external_userid, owner_userid, customer_name, remark
            FROM contacts
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (external_userid,),
        )
        row = cur.fetchone()
        contact = dict(row) if row else {}
    except Exception:
        db.rollback()
        contact = {}

    contact_owner = _text(contact.get("owner_userid"))
    if strict_owner_match and contact_owner and contact_owner != owner_userid:
        raise ExternalCampaignError(
            f"owner_mismatch:contact_owner={contact_owner}:requested_owner={owner_userid}",
            status_code=409,
        )
    return {"member": dict(member), "contact": contact}


def _existing_campaign_response(campaign_code: str) -> JsonDict | None:
    from wecom_ability_service.domains.campaigns import scheduler as campaign_scheduler
    from wecom_ability_service.domains.campaigns import service as campaign_service

    existing = campaign_service.get_campaign(campaign_code=campaign_code)
    if not existing:
        return None
    scheduled_jobs = _count_open_campaign_jobs(campaign_id=int(existing["id"]))
    if _text(existing.get("run_status")) == "active":
        campaign_scheduler.ensure_campaign_scheduled_jobs(campaign_id=int(existing["id"]))
        scheduled_jobs = _count_open_campaign_jobs(campaign_id=int(existing["id"]))
    return {
        "campaign_code": campaign_code,
        "campaign_id": int(existing["id"]),
        "status": "exists",
        "review_status": _text(existing.get("review_status")),
        "run_status": _text(existing.get("run_status")),
        "scheduled_jobs": scheduled_jobs,
    }


def _count_open_campaign_jobs(*, campaign_id: int) -> int:
    from wecom_ability_service.db import get_db

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS job_count
        FROM broadcast_jobs
        WHERE source_type = 'campaign'
          AND source_id LIKE ?
          AND status IN ('waiting_approval', 'queued', 'claimed')
        """,
        (f"{int(campaign_id)}:%",),
    )
    row = cur.fetchone()
    return int(row["job_count"] or 0) if row else 0


def _create_single_recipient_campaign(
    *,
    payload: JsonDict,
    recipient: JsonDict,
    owner_userid: str,
    operator: str,
    group_code: str,
    group_label: str,
    timezone_name: str,
    strict_owner_match: bool,
) -> JsonDict:
    from wecom_ability_service.domains.campaigns import service as campaign_service
    from wecom_ability_service.domains.segments import service as segment_service

    external_userid = _text(recipient["external_userid"])
    steps = _normalize_step_list(
        recipient.get("steps") if isinstance(recipient.get("steps"), list) else payload.get("steps"),
        payload,
        recipient,
        timezone_name=timezone_name,
    )
    first_dt = _parse_local_datetime(steps[0]["scheduled_for"], default_timezone=timezone_name)
    anchor_date = first_dt.date().isoformat()
    fingerprint = _hash_payload(
        payload.get("idempotency_key"),
        group_code,
        owner_userid,
        external_userid,
        anchor_date,
        steps,
    )
    campaign_code = _text(recipient.get("campaign_code")) or _text(payload.get("campaign_code"))
    if campaign_code and len(_normalize_recipients(payload)) > 1:
        campaign_code = f"{campaign_code}_{fingerprint[:8]}"
    campaign_code = campaign_code or f"camp_ext_{fingerprint}"
    existing = _existing_campaign_response(campaign_code)
    if existing:
        existing["external_userid"] = external_userid
        return existing

    target = _lookup_target(
        external_userid=external_userid,
        owner_userid=owner_userid,
        strict_owner_match=strict_owner_match,
    )
    segment_code = f"seg_ext_{fingerprint}"
    segment = segment_service.get_segment(segment_code=segment_code)
    if not segment:
        segment = segment_service.create_segment(
            segment_code=segment_code,
            display_name=f"{group_label} · {external_userid}",
            description="External token protected one-recipient campaign segment.",
            sql_query=_ONE_RECIPIENT_SEGMENT_SQL,
            sql_params={"external_userid": external_userid},
            source_type="external_campaign",
            tags=("external_campaign", owner_userid),
            operator=operator,
            session_id=_text(payload.get("session_id")),
            activate=True,
        )
    elif _text(segment.get("source_type")) == "external_campaign":
        segment = segment_service.update_segment(
            segment_code=segment_code,
            sql_query=_ONE_RECIPIENT_SEGMENT_SQL,
            sql_params={"external_userid": external_userid},
            operator=operator,
        )
    if int(segment.get("cached_headcount") or 0) != 1:
        raise ExternalCampaignError(
            f"target_headcount_invalid:{external_userid}:{segment.get('cached_headcount')}",
            status_code=409,
        )

    display_name = (
        _text(recipient.get("display_name"))
        or f"{group_label} · {external_userid} · {anchor_date}"
    )
    campaign = campaign_service.create_campaign_draft(
        campaign_code=campaign_code,
        display_name=display_name,
        intent=_text(payload.get("intent")) or group_label,
        anchor_mode="campaign_start_date",
        anchor_date=anchor_date,
        owner_userid=owner_userid,
        operator=operator,
        session_id=_text(payload.get("session_id")),
        trace_id=_text(payload.get("trace_id")) or f"ext-campaign-{fingerprint}",
        metadata={
            "source": "external_token_api",
            "group_code": group_code,
            "group_label": group_label,
            "external_userid": external_userid,
            "owner_userid": owner_userid,
            "idempotency_key": _text(payload.get("idempotency_key")),
            "contact": target.get("contact") or {},
        },
    )
    campaign_segment = campaign_service.add_segment_to_campaign(
        campaign_id=int(campaign["id"]),
        segment_code=segment_code,
        priority=int(payload.get("priority") or 100),
        label=_text(recipient.get("label")) or external_userid,
    )
    for step in steps:
        campaign_service.add_step_to_campaign(
            campaign_id=int(campaign["id"]),
            campaign_segment_id=int(campaign_segment["id"]),
            step_index=int(step["step_index"]),
            day_offset=int(step["day_offset"]),
            content_text=_text(step["content_text"]),
            content_payload=step["content_payload"],
            send_time=_text(step["send_time"]),
            timezone=_text(step["timezone"]) or timezone_name,
            stop_on_reply=bool(step["stop_on_reply"]),
            skip_if_recently_touched_days=int(step["skip_if_recently_touched_days"]),
            agent_run_id=_text(payload.get("agent_run_id")),
        )
    allocation = campaign_service.allocate_campaign_members(campaign_id=int(campaign["id"]))
    if int(allocation.get("allocated") or 0) != 1:
        try:
            campaign_service.delete_campaign(campaign_id=int(campaign["id"]))
        except Exception:
            pass
        raise ExternalCampaignError(
            (
                f"campaign_member_allocation_failed:{external_userid}:{allocation.get('allocated')}"
                f":errors={allocation.get('errors') or []}"
            ),
            status_code=409,
        )
    submitted = campaign_service.submit_campaign_for_review(campaign_id=int(campaign["id"]), operator=operator)
    scheduled_jobs = _count_open_campaign_jobs(campaign_id=int(submitted["id"]))
    return {
        "campaign_code": campaign_code,
        "campaign_id": int(submitted["id"]),
        "external_userid": external_userid,
        "segment_code": segment_code,
        "status": "created",
        "review_status": _text(submitted.get("review_status")),
        "run_status": _text(submitted.get("run_status")),
        "anchor_date": anchor_date,
        "first_scheduled_for": first_dt.isoformat(),
        "step_count": len(steps),
        "scheduled_jobs": scheduled_jobs,
        "requires_human_review": True,
    }


def _preview_single_recipient_campaign(
    *,
    payload: JsonDict,
    recipient: JsonDict,
    owner_userid: str,
    group_code: str,
    group_label: str,
    timezone_name: str,
    strict_owner_match: bool,
) -> JsonDict:
    external_userid = _text(recipient["external_userid"])
    steps = _normalize_step_list(
        recipient.get("steps") if isinstance(recipient.get("steps"), list) else payload.get("steps"),
        payload,
        recipient,
        timezone_name=timezone_name,
    )
    first_dt = _parse_local_datetime(steps[0]["scheduled_for"], default_timezone=timezone_name)
    anchor_date = first_dt.date().isoformat()
    fingerprint = _hash_payload(
        payload.get("idempotency_key"),
        group_code,
        owner_userid,
        external_userid,
        anchor_date,
        steps,
    )
    campaign_code = _text(recipient.get("campaign_code")) or _text(payload.get("campaign_code"))
    if campaign_code and len(_normalize_recipients(payload)) > 1:
        campaign_code = f"{campaign_code}_{fingerprint[:8]}"
    campaign_code = campaign_code or f"camp_ext_{fingerprint}"
    target = _lookup_target(
        external_userid=external_userid,
        owner_userid=owner_userid,
        strict_owner_match=strict_owner_match,
    )
    return {
        "campaign_code": campaign_code,
        "external_userid": external_userid,
        "segment_code": f"seg_ext_{fingerprint}",
        "anchor_date": anchor_date,
        "first_scheduled_for": first_dt.isoformat(),
        "step_count": len(steps),
        "steps": [
            {
                "step_index": int(step["step_index"]),
                "scheduled_for": _text(step["scheduled_for"]),
                "content_preview": _text(step["content_text"])[:120],
                "stop_on_reply": bool(step["stop_on_reply"]),
            }
            for step in steps
        ],
        "contact": target.get("contact") or {},
        "would_create": _existing_campaign_response(campaign_code) is None,
    }


def create_external_campaigns(payload: JsonDict) -> JsonDict:
    if not isinstance(payload, dict):
        raise ExternalCampaignError("json object body is required")
    owner_userid = _text(payload.get("owner_userid") or payload.get("sender"))
    if not owner_userid:
        raise ExternalCampaignError("owner_userid/sender is required")
    operator = _text(payload.get("operator")) or f"external:{owner_userid}"
    timezone_name = _text(payload.get("timezone")) or _DEFAULT_TIMEZONE
    group_code = _slug(payload.get("group_code") or payload.get("idempotency_key") or payload.get("intent"))
    group_label = _text(payload.get("group_label")) or _text(payload.get("intent")) or group_code
    strict_owner_match = not _truthy(payload.get("allow_owner_mismatch"))
    recipients = _normalize_recipients(payload)

    created: list[JsonDict] = []
    with _legacy_app().app_context():
        if _truthy(payload.get("dry_run")) or _truthy(payload.get("preview")):
            previews = [
                _preview_single_recipient_campaign(
                    payload=payload,
                    recipient=recipient,
                    owner_userid=owner_userid,
                    group_code=group_code,
                    group_label=group_label,
                    timezone_name=timezone_name,
                    strict_owner_match=strict_owner_match,
                )
                for recipient in recipients
            ]
            return {
                "ok": True,
                "dry_run": True,
                "side_effect_executed": False,
                "route_owner": "ai_crm_next",
                "source": "external_token_api",
                "group_code": group_code,
                "group_label": group_label,
                "owner_userid": owner_userid,
                "recipient_count": len(previews),
                "campaigns": previews,
            }
        for recipient in recipients:
            created.append(
                _create_single_recipient_campaign(
                    payload=payload,
                    recipient=recipient,
                    owner_userid=owner_userid,
                    operator=operator,
                    group_code=group_code,
                    group_label=group_label,
                    timezone_name=timezone_name,
                    strict_owner_match=strict_owner_match,
                )
            )
    return {
        "ok": True,
        "route_owner": "ai_crm_next",
        "source": "external_token_api",
        "group_code": group_code,
        "group_label": group_label,
        "owner_userid": owner_userid,
        "created_count": sum(1 for item in created if item.get("status") == "created"),
        "existing_count": sum(1 for item in created if item.get("status") == "exists"),
        "campaigns": created,
    }


def create_external_campaigns_response(payload: JsonDict, headers: Mapping[str, Any]) -> JsonDict | JSONResponse:
    failure = _auth_failure(headers)
    if failure is not None:
        error, status_code = failure
        return JSONResponse(
            {"ok": False, "error": error, "route_owner": "ai_crm_next"},
            status_code=status_code,
        )
    try:
        return create_external_campaigns(payload)
    except ExternalCampaignError as exc:
        return JSONResponse(
            {"ok": False, "error": exc.error, "route_owner": "ai_crm_next"},
            status_code=exc.status_code,
        )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "route_owner": "ai_crm_next"},
            status_code=500,
        )


def get_external_campaign_status(campaign_code: str) -> JsonDict:
    normalized_code = _text(campaign_code)
    if not normalized_code:
        raise ExternalCampaignError("campaign_code is required")
    with _legacy_app().app_context():
        from wecom_ability_service.domains.campaigns import service as campaign_service

        campaign = campaign_service.get_campaign(campaign_code=normalized_code)
        if not campaign:
            raise ExternalCampaignError("campaign_not_found", status_code=404)
        overview = campaign_service.assemble_campaign_overview(campaign_id=int(campaign["id"]))
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "campaign": overview.get("campaign") or campaign,
            "segments": overview.get("segments") or [],
            "member_status_counts": overview.get("member_status_counts") or {},
            "total_members": int(overview.get("total_members") or 0),
            "scheduled_jobs": _count_open_campaign_jobs(campaign_id=int(campaign["id"])),
        }


def get_external_campaign_status_response(campaign_code: str, headers: Mapping[str, Any]) -> JsonDict | JSONResponse:
    failure = _auth_failure(headers)
    if failure is not None:
        error, status_code = failure
        return JSONResponse(
            {"ok": False, "error": error, "route_owner": "ai_crm_next"},
            status_code=status_code,
        )
    try:
        return get_external_campaign_status(campaign_code)
    except ExternalCampaignError as exc:
        return JSONResponse(
            {"ok": False, "error": exc.error, "route_owner": "ai_crm_next"},
            status_code=exc.status_code,
        )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "route_owner": "ai_crm_next"},
            status_code=500,
        )
