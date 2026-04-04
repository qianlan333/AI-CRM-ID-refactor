from __future__ import annotations

from flask import jsonify, request

from ..customer_center.service import get_customer_detail
from ..customer_timeline.service import get_customer_timeline
from ..services import get_recent_messages_by_user, get_signup_conversion_batch, list_signup_conversion_batches


def _candidate_context(external_userid: str) -> dict[str, object]:
    timeline_limit = 20
    timeline = get_customer_timeline(
        external_userid,
        {
            "normalized_limit": timeline_limit,
            "normalized_offset": 0,
            "limit": timeline_limit,
            "offset": 0,
            "event_type": "",
        },
    ) or {
        "external_userid": external_userid,
        "items": [],
        "count": 0,
        "limit": timeline_limit,
        "offset": 0,
        "filters": {"event_type": "", "limit": str(timeline_limit), "offset": "0"},
        "total": 0,
    }
    return {
        "external_userid": external_userid,
        "customer": get_customer_detail(external_userid),
        "recent_messages": get_recent_messages_by_user(external_userid, limit=20),
        "timeline": timeline,
        "recent_timeline_events": timeline.get("items", []),
        "source_status": "live",
        "degraded": False,
        "warnings": [],
    }


def signup_conversion_batch_list():
    limit = request.args.get("limit", 20)
    cursor = str(request.args.get("cursor", "") or "")
    try:
        payload = list_signup_conversion_batches(limit=int(limit), cursor=cursor)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "automation_batches": payload})


def signup_conversion_batch_detail(batch_id: int):
    payload = get_signup_conversion_batch(batch_id)
    if not payload:
        return jsonify({"ok": False, "error": "batch not found"}), 404
    candidates = []
    for item in payload.get("candidates") or []:
        candidate = dict(item)
        external_userid = str(candidate.get("external_userid") or "").strip()
        candidate["customer_context"] = _candidate_context(external_userid) if external_userid else {}
        candidates.append(candidate)
    payload["candidates"] = candidates
    return jsonify({"ok": True, "automation_batch": payload})


def register_routes(bp):
    bp.route("/api/customers/automation/signup-conversion/batches", methods=["GET"])(signup_conversion_batch_list)
    bp.route("/api/customers/automation/signup-conversion/batches/<int:batch_id>", methods=["GET"])(
        signup_conversion_batch_detail
    )
