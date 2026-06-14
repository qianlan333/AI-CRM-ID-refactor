from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from aicrm_next.shared.postgres_connection import db_session, get_db

from . import process_event
from .domain import AutomationEventInput, EVENT_CHANNEL_ENTERED, EVENT_PAYMENT_SUCCEEDED, text
from .event_store import insert_event, mark_ignored


def _active_bindings(channel_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT b.*, p.status AS program_status
        FROM automation_program_channel_binding b
        INNER JOIN automation_program p ON p.id = b.program_id
        WHERE b.channel_id = ? AND b.binding_status = 'active' AND b.auto_enter_pool = TRUE
        ORDER BY b.priority DESC, b.bound_at DESC, b.id DESC
        """,
        (int(channel_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def process_channel_entry_event(
    *,
    channel_id: int,
    external_userid: str,
    event_log_id: int | None = None,
    payload_json: dict[str, Any] | None = None,
    occurred_at: Any = None,
) -> dict[str, Any]:
    with db_session():
        return _process_channel_entry_event(
            channel_id=channel_id,
            external_userid=external_userid,
            event_log_id=event_log_id,
            payload_json=payload_json,
            occurred_at=occurred_at,
        )


def _process_channel_entry_event(
    *,
    channel_id: int,
    external_userid: str,
    event_log_id: int | None = None,
    payload_json: dict[str, Any] | None = None,
    occurred_at: Any = None,
) -> dict[str, Any]:
    bindings = _active_bindings(int(channel_id))
    source_base = str(event_log_id or f"{int(channel_id)}:{text(external_userid)}:{text(occurred_at)}")
    if not bindings:
        event = insert_event(
            AutomationEventInput(
                event_type=EVENT_CHANNEL_ENTERED,
                source_type="wecom_channel_callback",
                source_id=source_base,
                idempotency_key=f"wecom_channel_callback:{source_base}",
                channel_id=int(channel_id),
                external_userid=text(external_userid),
                occurred_at=occurred_at,
                payload_json=dict(payload_json or {}),
            )
        )
        mark_ignored(int(event["id"]), "no_active_binding")
        get_db().commit()
        return {"ok": True, "reason": "no_active_binding", "event_id": int(event["id"]), "processed": []}
    processed = []
    for binding in bindings:
        if text(binding.get("program_status")) == "archived":
            continue
        source_id = source_base if len(bindings) == 1 else f"{source_base}:{int(binding['id'])}"
        event = insert_event(
            AutomationEventInput(
                event_type=EVENT_CHANNEL_ENTERED,
                source_type="wecom_channel_callback",
                source_id=source_id,
                idempotency_key=f"wecom_channel_callback:{source_id}",
                program_id=int(binding["program_id"]),
                channel_id=int(channel_id),
                binding_id=int(binding["id"]),
                external_userid=text(external_userid),
                occurred_at=occurred_at,
                payload_json=dict(payload_json or {}),
            )
        )
        processed.append(process_event(int(event["id"])))
    return {"ok": True, "reason": "processed", "processed": processed}


def process_payment_succeeded_event(*, order: dict[str, Any], transaction: dict[str, Any] | None = None) -> dict[str, Any]:
    order_id = text(order.get("out_trade_no") or order.get("id") or (transaction or {}).get("out_trade_no"))
    payload_json = _json_safe(
        {
            "order_id": order_id,
            "product_id": order.get("product_id") or order.get("product_code"),
            "amount": order.get("amount_total") or order.get("payer_total"),
            "paid_at": order.get("paid_at"),
            "transaction": dict(transaction or {}),
        }
    )
    event = insert_event(
        AutomationEventInput(
            event_type=EVENT_PAYMENT_SUCCEEDED,
            source_type="payment",
            source_id=order_id,
            idempotency_key=f"payment:{order_id}",
            external_userid=text(order.get("external_userid") or order.get("userid_snapshot")),
            phone=text(order.get("mobile_snapshot") or order.get("respondent_key")),
            payload_json=payload_json if isinstance(payload_json, dict) else {},
        )
    )
    return process_event(int(event["id"]))
