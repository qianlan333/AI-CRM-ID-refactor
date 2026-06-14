from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from decimal import Decimal

from aicrm_next.automation_runtime_v2.bridge import process_payment_succeeded_event
from tests.automation_runtime_v2_test_helpers import count, db, ensure_runtime_v2_base_tables


def _payment_order(out_trade_no: str = "WXP_JSON_SAFE") -> dict:
    return {
        "id": 143,
        "out_trade_no": out_trade_no,
        "product_code": "subscription_trial_month",
        "amount_total": Decimal("990"),
        "payer_total": Decimal("990"),
        "external_userid": "wm_json_safe",
        "userid_snapshot": "user_json_safe",
        "mobile_snapshot": "13800001234",
        "respondent_key": "respondent_json_safe",
        "paid_at": datetime(2026, 6, 14, 12, 42, 36, tzinfo=timezone.utc),
    }


def _transaction(out_trade_no: str = "WXP_JSON_SAFE") -> dict:
    return {
        "out_trade_no": out_trade_no,
        "trade_state": "SUCCESS",
        "transaction_id": "wx_tx_json_safe",
        "success_time": datetime(2026, 6, 14, 12, 43, 1, tzinfo=timezone.utc),
        "amount": {"payer_total": Decimal("990.50")},
        "nested": {
            "dates": [
                datetime(2026, 6, 14, 12, 44, 1, tzinfo=timezone.utc),
                date(2026, 6, 14),
                time(12, 45, 2),
            ],
            "set_value": {Decimal("1"), Decimal("2")},
        },
    }


def test_payment_succeeded_event_normalizes_payment_payload_before_insert(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_insert_event(payload):
        json.dumps(payload.payload_json, ensure_ascii=False)
        captured.append(
            {
                "source_id": payload.source_id,
                "idempotency_key": payload.idempotency_key,
                "external_userid": payload.external_userid,
                "phone": payload.phone,
                "payload_json": payload.payload_json,
            }
        )
        return {"id": 42}

    monkeypatch.setattr("aicrm_next.automation_runtime_v2.bridge.insert_event", fake_insert_event)
    monkeypatch.setattr("aicrm_next.automation_runtime_v2.bridge.process_event", lambda event_id: {"event_id": event_id})

    result = process_payment_succeeded_event(order=_payment_order(), transaction=_transaction())
    payload = captured[0]["payload_json"]

    assert result["event_id"] == 42
    assert captured[0]["source_id"] == "WXP_JSON_SAFE"
    assert captured[0]["idempotency_key"] == "payment:WXP_JSON_SAFE"
    assert captured[0]["external_userid"] == "wm_json_safe"
    assert captured[0]["phone"] == "13800001234"
    assert payload["paid_at"] == "2026-06-14T12:42:36+00:00"
    assert payload["transaction"]["success_time"] == "2026-06-14T12:43:01+00:00"
    assert payload["transaction"]["nested"]["dates"][0] == "2026-06-14T12:44:01+00:00"
    assert payload["transaction"]["amount"]["payer_total"] == 990.5
    assert sorted(payload["transaction"]["nested"]["set_value"]) == [1, 2]


def _stored_payment_payload(out_trade_no: str = "WXP_JSON_SAFE") -> dict:
    row = db().execute(
        """
        SELECT payload_json
        FROM automation_event_v2
        WHERE source_type = 'payment' AND source_id = ?
        LIMIT 1
        """,
        (out_trade_no,),
    ).fetchone()
    assert row is not None
    return dict(row["payload_json"])


def test_payment_succeeded_event_accepts_datetime_and_decimal_payload(next_pg_schema) -> None:
    ensure_runtime_v2_base_tables()

    result = process_payment_succeeded_event(order=_payment_order(), transaction=_transaction())
    payload = _stored_payment_payload()

    assert result["event_id"] > 0
    assert payload["paid_at"] == "2026-06-14T12:42:36+00:00"
    assert payload["transaction"]["success_time"] == "2026-06-14T12:43:01+00:00"
    assert payload["transaction"]["nested"]["dates"][0] == "2026-06-14T12:44:01+00:00"
    assert payload["transaction"]["nested"]["dates"][1] == "2026-06-14"
    assert payload["transaction"]["nested"]["dates"][2] == "12:45:02"
    assert payload["amount"] == 990
    assert payload["transaction"]["amount"]["payer_total"] == 990.5
    assert sorted(payload["transaction"]["nested"]["set_value"]) == [1, 2]


def test_payment_succeeded_event_is_idempotent_by_out_trade_no(next_pg_schema) -> None:
    ensure_runtime_v2_base_tables()

    first = process_payment_succeeded_event(order=_payment_order("WXP_JSON_SAFE_IDEMPOTENT"), transaction=_transaction("WXP_JSON_SAFE_IDEMPOTENT"))
    second = process_payment_succeeded_event(order=_payment_order("WXP_JSON_SAFE_IDEMPOTENT"), transaction=_transaction("WXP_JSON_SAFE_IDEMPOTENT"))
    rows = db().execute(
        """
        SELECT id, idempotency_key
        FROM automation_event_v2
        WHERE source_type = 'payment' AND source_id = 'WXP_JSON_SAFE_IDEMPOTENT'
        ORDER BY id ASC
        """
    ).fetchall()

    assert first["event_id"] == second["event_id"]
    assert len(rows) == 1
    assert rows[0]["idempotency_key"] == "payment:WXP_JSON_SAFE_IDEMPOTENT"
    assert count("automation_event_v2") == 1
