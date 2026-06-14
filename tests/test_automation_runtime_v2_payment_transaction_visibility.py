from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from flask import has_app_context

from aicrm_next.automation_runtime_v2.bridge import process_payment_succeeded_event
from tests.automation_runtime_v2_test_helpers import count, db, ensure_runtime_v2_base_tables


def _order(out_trade_no: str = "WXP_VISIBILITY") -> dict:
    return {
        "id": 143,
        "out_trade_no": out_trade_no,
        "product_code": "subscription_trial_month",
        "amount_total": Decimal("990"),
        "external_userid": "wm_visibility",
        "userid_snapshot": "user_visibility",
        "mobile_snapshot": "13800001234",
        "respondent_key": "respondent_visibility",
        "paid_at": datetime(2026, 6, 14, 12, 42, 36, tzinfo=timezone.utc),
    }


def _transaction(out_trade_no: str = "WXP_VISIBILITY") -> dict:
    return {
        "out_trade_no": out_trade_no,
        "trade_state": "SUCCESS",
        "transaction_id": "wx_tx_visibility",
        "success_time": datetime(2026, 6, 14, 12, 43, 1, tzinfo=timezone.utc),
        "amount": {"payer_total": Decimal("990.50")},
        "nested": {"seen_at": [datetime(2026, 6, 14, 12, 44, 1, tzinfo=timezone.utc)]},
    }


def _stored_payment_event(out_trade_no: str = "WXP_VISIBILITY") -> dict:
    row = db().execute(
        """
        SELECT id, event_type, source_type, source_id, idempotency_key, status, error_message, payload_json
        FROM automation_event_v2
        WHERE source_type = 'payment' AND source_id = ?
        LIMIT 1
        """,
        (out_trade_no,),
    ).fetchone()
    assert row is not None
    return dict(row)


def test_payment_insert_is_visible_to_process_event_without_flask_context(next_pg_schema) -> None:
    ensure_runtime_v2_base_tables()
    assert has_app_context() is False

    result = process_payment_succeeded_event(order=_order(), transaction=_transaction())
    event = _stored_payment_event()

    assert result["event_id"] == event["id"]
    assert result["status"] == "ignored"
    assert result["reason"] == "membership_unresolved"
    assert event["event_type"] == "payment_succeeded"
    assert event["source_id"] == "WXP_VISIBILITY"
    assert event["idempotency_key"] == "payment:WXP_VISIBILITY"
    assert event["status"] == "ignored"
    assert event["error_message"] == "membership_unresolved"
    json.dumps(event["payload_json"], ensure_ascii=False)
    assert event["payload_json"]["paid_at"] == "2026-06-14T12:42:36+00:00"
    assert event["payload_json"]["transaction"]["success_time"] == "2026-06-14T12:43:01+00:00"
    assert event["payload_json"]["transaction"]["nested"]["seen_at"][0] == "2026-06-14T12:44:01+00:00"


def test_payment_visibility_path_is_idempotent_by_out_trade_no(next_pg_schema) -> None:
    ensure_runtime_v2_base_tables()

    first = process_payment_succeeded_event(order=_order("WXP_VISIBILITY_IDEMPOTENT"), transaction=_transaction("WXP_VISIBILITY_IDEMPOTENT"))
    second = process_payment_succeeded_event(order=_order("WXP_VISIBILITY_IDEMPOTENT"), transaction=_transaction("WXP_VISIBILITY_IDEMPOTENT"))
    rows = db().execute(
        """
        SELECT id, idempotency_key, status
        FROM automation_event_v2
        WHERE source_type = 'payment' AND source_id = 'WXP_VISIBILITY_IDEMPOTENT'
        ORDER BY id ASC
        """
    ).fetchall()

    assert first["event_id"] == second["event_id"]
    assert len(rows) == 1
    assert rows[0]["idempotency_key"] == "payment:WXP_VISIBILITY_IDEMPOTENT"
    assert rows[0]["status"] == "ignored"
    assert count("automation_event_v2") == 1
