from __future__ import annotations

from flask import jsonify, request

from ..customer_center.service import get_customer_detail
from ..customer_timeline.service import get_customer_timeline
from ..services import (
    apply_activation_webhook,
    get_recent_messages_by_user,
    get_signup_conversion_batch,
    list_outbound_webhook_deliveries,
    list_signup_conversion_batches,
    retry_outbound_webhook_delivery,
    run_due_outbound_webhook_retries,
)
from .internal_auth import require_internal_api_token


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

def activation_webhook():
    auth_failure = require_internal_api_token(
        token_keys=("AUTOMATION_ACTIVATION_WEBHOOK_TOKEN",),
        legacy_header_names=("X-Automation-Token",),
    )
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    mobile = str(payload.get("mobile") or "").strip()
    activated_at = str(payload.get("activated_at") or payload.get("last_activation_at") or "").strip()
    operator = str(payload.get("operator") or "").strip() or "activation_webhook"
    source = str(payload.get("source") or "").strip() or "activation_webhook"
    try:
        result = apply_activation_webhook(
            mobile=mobile,
            activated_at=activated_at,
            operator=operator,
            source=source,
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def webhook_delivery_list():
    event_type = str(request.args.get("event_type", "") or "")
    status = str(request.args.get("status", "") or "")
    limit = request.args.get("limit", 50)
    try:
        payload = list_outbound_webhook_deliveries(
            event_type=event_type,
            status=status,
            limit=int(limit),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "deliveries": payload})


def webhook_delivery_retry(delivery_id: int):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    try:
        payload = retry_outbound_webhook_delivery(int(delivery_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "delivery": payload})


def webhook_delivery_retry_due():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    limit = payload.get("limit", request.args.get("limit", 20))
    try:
        result = run_due_outbound_webhook_retries(limit=int(limit))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def register_routes(bp):
    bp.route("/api/customers/automation/signup-conversion/batches", methods=["GET"])(signup_conversion_batch_list)
    bp.route("/api/customers/automation/signup-conversion/batches/<int:batch_id>", methods=["GET"])(
        signup_conversion_batch_detail
    )
    bp.route("/api/customers/automation/activation-webhook", methods=["POST"])(activation_webhook)
    bp.route("/api/customers/automation/webhook-deliveries", methods=["GET"])(webhook_delivery_list)
    bp.route("/api/customers/automation/webhook-deliveries/<int:delivery_id>/retry", methods=["POST"])(webhook_delivery_retry)
    bp.route("/api/customers/automation/webhook-deliveries/retry-due", methods=["POST"])(webhook_delivery_retry_due)
