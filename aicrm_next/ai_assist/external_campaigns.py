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
_TABLE_COLUMNS_CACHE: dict[str, set[str]] = {}

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
    def __init__(
        self,
        error: str,
        *,
        status_code: int = 400,
        message: str = "",
        phase: str = "",
        external_userid: str = "",
        owner_userid: str = "",
        group_code: str = "",
        campaign_code: str = "",
        trace_id: str = "",
        details: JsonDict | None = None,
    ) -> None:
        super().__init__(message or error)
        self.error = error
        self.status_code = status_code
        self.phase = phase
        self.external_userid = external_userid
        self.owner_userid = owner_userid
        self.group_code = group_code
        self.campaign_code = campaign_code
        self.trace_id = trace_id
        self.details = details or {}

    def add_context(
        self,
        *,
        group_code: str = "",
        campaign_code: str = "",
        trace_id: str = "",
        owner_userid: str = "",
        external_userid: str = "",
    ) -> "ExternalCampaignError":
        if group_code and not self.group_code:
            self.group_code = group_code
        if campaign_code and not self.campaign_code:
            self.campaign_code = campaign_code
        if trace_id and not self.trace_id:
            self.trace_id = trace_id
        if owner_userid and not self.owner_userid:
            self.owner_userid = owner_userid
        if external_userid and not self.external_userid:
            self.external_userid = external_userid
        return self

    def to_response(self) -> JsonDict:
        payload: JsonDict = {
            "ok": False,
            "error": self.error,
            "route_owner": "ai_crm_next",
        }
        if str(self):
            payload["message"] = str(self)
        for key in ("phase", "external_userid", "owner_userid", "group_code", "campaign_code", "trace_id"):
            value = _text(getattr(self, key))
            if value:
                payload[key] = value
        payload.update(self.details)
        return payload


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


def _row_dict(row: Any) -> JsonDict:
    return dict(row) if row else {}


def _table_columns(table_name: str) -> set[str]:
    if table_name in _TABLE_COLUMNS_CACHE:
        return _TABLE_COLUMNS_CACHE[table_name]
    from wecom_ability_service.db import get_db

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table_name,),
        )
        rows = cur.fetchall() or []
        columns = {_text(row["column_name"]) for row in rows if _text(row["column_name"])}
        if columns:
            _TABLE_COLUMNS_CACHE[table_name] = columns
            return columns
    except Exception:
        db.rollback()
    try:
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = {_text(row["name"]) for row in cur.fetchall() or [] if _text(row["name"])}
        _TABLE_COLUMNS_CACHE[table_name] = columns
        return columns
    except Exception:
        db.rollback()
    return set()


def _fetch_user_ops_pool_current_row(cur: Any, external_userid: str) -> JsonDict:
    cur.execute(
        """
        SELECT *
        FROM user_ops_pool_current
        WHERE external_userid = ?
        LIMIT 1
        """,
        (external_userid,),
    )
    return _row_dict(cur.fetchone())


def _fetch_automation_member_row(cur: Any, external_userid: str) -> JsonDict:
    cur.execute(
        """
        SELECT id, external_contact_id, owner_staff_id
        FROM automation_member
        WHERE external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (external_userid,),
    )
    return _row_dict(cur.fetchone())


def _fetch_contact_row(cur: Any, external_userid: str) -> JsonDict:
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
    return _row_dict(cur.fetchone())


def _lookup_target(*, external_userid: str, owner_userid: str, strict_owner_match: bool) -> JsonDict:
    from wecom_ability_service.db import get_db

    db = get_db()
    cur = db.cursor()
    pool_current = _fetch_user_ops_pool_current_row(cur, external_userid)
    member = _fetch_automation_member_row(cur, external_userid)
    contact: JsonDict = {}
    try:
        contact = _fetch_contact_row(cur, external_userid)
    except Exception:
        db.rollback()
        contact = {}

    contact_owner = _text(contact.get("owner_userid"))
    if strict_owner_match and contact_owner and contact_owner != owner_userid:
        raise ExternalCampaignError(
            "owner_mismatch",
            status_code=409,
            message=f"owner_mismatch:contact_owner={contact_owner}:requested_owner={owner_userid}",
            phase="target_lookup",
            external_userid=external_userid,
            owner_userid=owner_userid,
        )
    if not pool_current and not member:
        raise ExternalCampaignError(
            "target_not_found",
            status_code=404,
            message=f"target_not_found:{external_userid}",
            phase="target_lookup",
            external_userid=external_userid,
            owner_userid=owner_userid,
        )
    return {
        "resolved": True,
        "source": "user_ops_pool_current" if pool_current else "automation_member",
        "pool_current": pool_current,
        "member": member,
        "contact": contact,
    }


def _backfill_source_for_external_userid(cur: Any, external_userid: str) -> JsonDict:
    contact: JsonDict = {}
    pool_current: JsonDict = {}
    try:
        contact = _fetch_contact_row(cur, external_userid)
    except Exception:
        from wecom_ability_service.db import get_db

        get_db().rollback()
        contact = {}
    try:
        pool_current = _fetch_user_ops_pool_current_row(cur, external_userid)
    except Exception:
        from wecom_ability_service.db import get_db

        get_db().rollback()
        pool_current = {}
    if not contact and not pool_current:
        from wecom_ability_service.domains.automation_conversion import automation_member_backfill_service

        candidate = automation_member_backfill_service.get_sidebar_binding_campaign_candidate(external_userid)
        if candidate is None:
            return {}
        return {
            "source": "sidebar_binding",
            "external_userid": external_userid,
            "owner_userid": candidate.owner_staff_id,
            "customer_name": candidate.customer_name,
            "mobile": candidate.phone,
            "contact": {},
            "pool_current": {},
        }
    source = "contacts" if contact else "user_ops_pool_current"
    owner = _text((contact if contact else pool_current).get("owner_userid"))
    if not owner:
        owner = _text(pool_current.get("owner_userid"))
    return {
        "source": source,
        "external_userid": external_userid,
        "owner_userid": owner,
        "customer_name": _text(contact.get("customer_name")) or _text(pool_current.get("customer_name")),
        "remark": _text(contact.get("remark")),
        "mobile": _text(pool_current.get("mobile")),
        "contact": contact,
        "pool_current": pool_current,
    }


def _insert_automation_member_from_backfill_source(
    cur: Any,
    *,
    external_userid: str,
    owner_userid: str,
    source: JsonDict,
) -> None:
    columns = _table_columns("automation_member")
    values: JsonDict = {
        "external_contact_id": external_userid,
        "phone": _text(source.get("mobile")),
        "owner_staff_id": owner_userid,
        "in_pool": True,
        "current_pool": "operating",
        "current_audience_code": "operating",
        "source_type": "external_campaign_backfill",
        "joined_at": "CURRENT_TIMESTAMP_TEXT",
        "created_at": "CURRENT_TIMESTAMP",
        "updated_at": "CURRENT_TIMESTAMP",
    }
    insert_columns = [column for column in values if column in columns or not columns]
    if "external_contact_id" not in insert_columns:
        raise RuntimeError("automation_member.external_contact_id column is required")

    placeholders = []
    params: list[Any] = []
    for column in insert_columns:
        value = values[column]
        if value == "CURRENT_TIMESTAMP":
            placeholders.append("CURRENT_TIMESTAMP")
        elif value == "CURRENT_TIMESTAMP_TEXT":
            placeholders.append("CAST(CURRENT_TIMESTAMP AS TEXT)")
        else:
            placeholders.append("?")
            params.append(value)
    cur.execute(
        f"""
        INSERT INTO automation_member ({", ".join(insert_columns)})
        VALUES ({", ".join(placeholders)})
        """,
        tuple(params),
    )


def backfill_automation_members_for_external_campaign(
    *,
    owner_userid: str,
    external_userids: list[str],
    operator: str = "",
    dry_run: bool = True,
    allow_owner_mismatch: bool = False,
) -> JsonDict:
    from wecom_ability_service.db import get_db

    normalized_owner = _text(owner_userid)
    seen: set[str] = set()
    targets = []
    for external_userid in external_userids:
        normalized = _text(external_userid)
        if normalized and normalized not in seen:
            seen.add(normalized)
            targets.append(normalized)

    db = get_db()
    cur = db.cursor()
    results: list[JsonDict] = []
    for external_userid in targets:
        existing = _fetch_automation_member_row(cur, external_userid)
        if existing:
            results.append(
                {
                    "external_userid": external_userid,
                    "status": "exists",
                    "source": "automation_member",
                    "automation_member_id": int(existing.get("id") or 0),
                    "owner_userid": _text(existing.get("owner_staff_id")),
                }
            )
            continue

        source = _backfill_source_for_external_userid(cur, external_userid)
        if not source:
            results.append(
                {
                    "external_userid": external_userid,
                    "status": "unresolved",
                    "source": "",
                    "owner_userid": "",
                }
            )
            continue

        source_owner = _text(source.get("owner_userid"))
        if source_owner and normalized_owner and source_owner != normalized_owner and not allow_owner_mismatch:
            results.append(
                {
                    "external_userid": external_userid,
                    "status": "owner_mismatch",
                    "source": _text(source.get("source")),
                    "owner_userid": source_owner,
                    "requested_owner_userid": normalized_owner,
                    "customer_name": _text(source.get("customer_name")),
                }
            )
            continue

        result = {
            "external_userid": external_userid,
            "status": "would_insert" if dry_run else "inserted",
            "source": _text(source.get("source")),
            "owner_userid": source_owner or normalized_owner,
            "requested_owner_userid": normalized_owner,
            "customer_name": _text(source.get("customer_name")),
            "operator": _text(operator),
            "target": source,
        }
        if not dry_run:
            if _text(source.get("source")) == "sidebar_binding":
                from wecom_ability_service.domains.automation_conversion import automation_member_backfill_service

                automation_member_backfill_service.ensure_campaign_member_from_sidebar_binding(
                    external_userid,
                    dry_run=False,
                    commit=False,
                )
            else:
                _insert_automation_member_from_backfill_source(
                    cur,
                    external_userid=external_userid,
                    owner_userid=source_owner or normalized_owner,
                    source=source,
                )
        results.append(result)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    status_counts = {status: sum(1 for item in results if item["status"] == status) for status in sorted({item["status"] for item in results})}
    return {
        "ok": True,
        "dry_run": dry_run,
        "owner_userid": normalized_owner,
        "operator": _text(operator),
        "total": len(targets),
        "status_counts": status_counts,
        "exists_count": status_counts.get("exists", 0),
        "would_insert_count": status_counts.get("would_insert", 0),
        "inserted_count": status_counts.get("inserted", 0),
        "unresolved_count": status_counts.get("unresolved", 0),
        "owner_mismatch_count": status_counts.get("owner_mismatch", 0),
        "results": results,
    }


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


def _cleanup_campaign_after_failed_create(*, campaign_id: int) -> JsonDict:
    from wecom_ability_service.domains.campaigns import service as campaign_service

    try:
        result = campaign_service.delete_campaign(campaign_id=int(campaign_id))
        return {"cleanup_ok": True, "cleanup_result": result}
    except Exception as exc:  # pragma: no cover - defensive cleanup path
        return {"cleanup_ok": False, "cleanup_error": str(exc)}


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
    trace_id = _text(payload.get("trace_id")) or f"ext-campaign-{fingerprint}"
    existing = _existing_campaign_response(campaign_code)
    if existing:
        existing["external_userid"] = external_userid
        return existing

    try:
        target = _lookup_target(
            external_userid=external_userid,
            owner_userid=owner_userid,
            strict_owner_match=strict_owner_match,
        )
    except ExternalCampaignError as exc:
        raise exc.add_context(group_code=group_code, campaign_code=campaign_code, trace_id=trace_id) from exc
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
            "target_headcount_invalid",
            status_code=409,
            message=f"target_headcount_invalid:{external_userid}:{segment.get('cached_headcount')}",
            phase="target_lookup",
            external_userid=external_userid,
            owner_userid=owner_userid,
            group_code=group_code,
            campaign_code=campaign_code,
            trace_id=trace_id,
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
        trace_id=trace_id,
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
    campaign_id = int(campaign["id"])
    try:
        campaign_segment = campaign_service.add_segment_to_campaign(
            campaign_id=campaign_id,
            segment_code=segment_code,
            priority=int(payload.get("priority") or 100),
            label=_text(recipient.get("label")) or external_userid,
        )
        for step in steps:
            campaign_service.add_step_to_campaign(
                campaign_id=campaign_id,
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
        allocation = campaign_service.allocate_campaign_members(campaign_id=campaign_id)
        if int(allocation.get("allocated") or 0) != 1:
            cleanup = _cleanup_campaign_after_failed_create(campaign_id=campaign_id)
            raise ExternalCampaignError(
                "campaign_member_allocation_failed",
                status_code=409,
                message=(
                    f"campaign_member_allocation_failed:{external_userid}:{allocation.get('allocated')}"
                    f":errors={allocation.get('errors') or []}"
                ),
                phase="allocation",
                external_userid=external_userid,
                owner_userid=owner_userid,
                group_code=group_code,
                campaign_code=campaign_code,
                trace_id=trace_id,
                details={
                    "allocation": allocation,
                    "allocation_errors": allocation.get("errors") or [],
                    **cleanup,
                },
            )
        submitted = campaign_service.submit_campaign_for_review(campaign_id=campaign_id, operator=operator)
    except ExternalCampaignError:
        raise
    except Exception as exc:
        cleanup = _cleanup_campaign_after_failed_create(campaign_id=campaign_id)
        raise ExternalCampaignError(
            "campaign_create_failed",
            status_code=500,
            message=str(exc),
            phase="campaign_create",
            external_userid=external_userid,
            owner_userid=owner_userid,
            group_code=group_code,
            campaign_code=campaign_code,
            trace_id=trace_id,
            details=cleanup,
        ) from exc
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
    target_override: JsonDict | None = None,
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
    trace_id = _text(payload.get("trace_id")) or f"ext-campaign-{fingerprint}"
    try:
        target = target_override or _lookup_target(
            external_userid=external_userid,
            owner_userid=owner_userid,
            strict_owner_match=strict_owner_match,
        )
    except ExternalCampaignError as exc:
        raise exc.add_context(group_code=group_code, campaign_code=campaign_code, trace_id=trace_id) from exc
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
        "target_source": _text(target.get("source")),
        "automation_member_backfill": target.get("automation_member_backfill") or {},
        "would_create": _existing_campaign_response(campaign_code) is None,
    }


def _public_backfill_result(item: JsonDict) -> JsonDict:
    return {key: value for key, value in item.items() if key != "target"}


def _auto_backfill_for_recipients(
    *,
    recipients: list[JsonDict],
    owner_userid: str,
    operator: str,
    dry_run: bool,
    allow_owner_mismatch: bool,
) -> tuple[list[JsonDict], JsonDict, dict[str, JsonDict]]:
    external_userids = [_text(recipient.get("external_userid")) for recipient in recipients]
    backfill = backfill_automation_members_for_external_campaign(
        owner_userid=owner_userid,
        external_userids=external_userids,
        operator=operator,
        dry_run=dry_run,
        allow_owner_mismatch=allow_owner_mismatch,
    )
    by_external = {_text(item.get("external_userid")): item for item in backfill.get("results") or []}
    allowed_statuses = {"exists", "would_insert"} if dry_run else {"exists", "inserted"}
    resolved_recipients: list[JsonDict] = []
    skipped: list[JsonDict] = []
    target_overrides: dict[str, JsonDict] = {}
    for recipient in recipients:
        external_userid = _text(recipient.get("external_userid"))
        result = by_external.get(external_userid) or {"external_userid": external_userid, "status": "unresolved"}
        status = _text(result.get("status"))
        if status in allowed_statuses:
            resolved_recipients.append(recipient)
            target = result.get("target")
            if isinstance(target, dict):
                target_overrides[external_userid] = {
                    "resolved": True,
                    "source": _text(target.get("source")),
                    "pool_current": target.get("pool_current") or {},
                    "member": {},
                    "contact": target.get("contact") or {},
                    "automation_member_backfill": _public_backfill_result(result),
                }
        else:
            skipped.append(_public_backfill_result(result))
    public_results = [_public_backfill_result(item) for item in backfill.get("results") or []]
    backfill_summary = {
        key: value
        for key, value in backfill.items()
        if key not in {"results"}
    }
    backfill_summary["results"] = public_results
    backfill_summary["resolved_count"] = len(resolved_recipients)
    backfill_summary["skipped_count"] = len(skipped)
    return resolved_recipients, {
        "backfill_summary": backfill_summary,
        "resolved_count": len(resolved_recipients),
        "skipped_count": len(skipped),
        "skipped_recipients": skipped,
        "owner_mismatch_count": int(backfill.get("owner_mismatch_count") or 0),
        "unresolved_count": int(backfill.get("unresolved_count") or 0),
    }, target_overrides


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
    dry_run = _truthy(payload.get("dry_run")) or _truthy(payload.get("preview"))
    auto_backfill = _truthy(payload.get("auto_backfill_automation_member"))

    created: list[JsonDict] = []
    with _legacy_app().app_context():
        backfill_response: JsonDict = {}
        target_overrides: dict[str, JsonDict] = {}
        effective_recipients = recipients
        if auto_backfill:
            effective_recipients, backfill_response, target_overrides = _auto_backfill_for_recipients(
                recipients=recipients,
                owner_userid=owner_userid,
                operator=operator,
                dry_run=dry_run,
                allow_owner_mismatch=not strict_owner_match,
            )
        if dry_run:
            previews = [
                _preview_single_recipient_campaign(
                    payload=payload,
                    recipient=recipient,
                    owner_userid=owner_userid,
                    group_code=group_code,
                    group_label=group_label,
                    timezone_name=timezone_name,
                    strict_owner_match=strict_owner_match,
                    target_override=target_overrides.get(_text(recipient.get("external_userid"))),
                )
                for recipient in effective_recipients
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
                **backfill_response,
            }
        for recipient in effective_recipients:
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
        **backfill_response,
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
        if isinstance(payload, dict):
            exc.add_context(
                group_code=_slug(payload.get("group_code") or payload.get("idempotency_key") or payload.get("intent")),
                trace_id=_text(payload.get("trace_id")),
                owner_userid=_text(payload.get("owner_userid") or payload.get("sender")),
            )
        return JSONResponse(
            exc.to_response(),
            status_code=exc.status_code,
        )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": "internal_error", "message": str(exc), "route_owner": "ai_crm_next"},
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
            exc.to_response(),
            status_code=exc.status_code,
        )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": "internal_error", "message": str(exc), "route_owner": "ai_crm_next"},
            status_code=500,
        )
