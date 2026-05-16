from __future__ import annotations

from typing import Any

from ...db import get_db
from ...infra.json_utils import json_dumps


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def insert_order(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no,
            order_source,
            client_order_ref,
            product_code,
            product_name,
            description,
            amount_total,
            currency,
            payer_openid,
            respondent_key,
            unionid,
            external_userid,
            status,
            success_url,
            metadata_json,
            request_meta_json,
            expires_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), ?::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("out_trade_no")),
            _normalized_text(payload.get("order_source")) or "h5_checkout",
            _normalized_text(payload.get("client_order_ref")),
            _normalized_text(payload.get("product_code")),
            _normalized_text(payload.get("product_name")),
            _normalized_text(payload.get("description")),
            int(payload.get("amount_total") or 0),
            _normalized_text(payload.get("currency")) or "CNY",
            _normalized_text(payload.get("payer_openid")),
            _normalized_text(payload.get("respondent_key")),
            _normalized_text(payload.get("unionid")),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")) or "created",
            _normalized_text(payload.get("success_url")),
            _json(payload.get("metadata") or {}),
            _json(payload.get("request_meta") or {}),
            _normalized_text(payload.get("expires_at")) or None,
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_order_payment_request(
    out_trade_no: str,
    *,
    prepay_id: str,
    status: str = "paying",
    request_payload: dict[str, Any] | None = None,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET prepay_id = ?,
            status = ?,
            request_payload_json = CAST(? AS jsonb),
            response_payload_json = CAST(? AS jsonb),
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (
            _normalized_text(prepay_id),
            _normalized_text(status) or "paying",
            _json(request_payload or {}),
            _json(response_payload or {}),
            _normalized_text(out_trade_no),
        ),
    ).fetchone()
    return dict(row) if row else {}


def mark_order_failed(out_trade_no: str, *, error_message: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET status = 'failed',
            last_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (_normalized_text(error_message)[:500], _normalized_text(out_trade_no)),
    ).fetchone()
    return dict(row) if row else {}


def get_order(out_trade_no: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM wechat_pay_orders
        WHERE out_trade_no = ?
        LIMIT 1
        """,
        (_normalized_text(out_trade_no),),
    )


def update_order_from_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    trade_state = _normalized_text(transaction.get("trade_state"))
    status = "paid" if trade_state == "SUCCESS" else ("closed" if trade_state in {"CLOSED", "REVOKED"} else "paying")
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    payer = transaction.get("payer") if isinstance(transaction.get("payer"), dict) else {}
    row = get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET status = ?,
            trade_state = ?,
            transaction_id = ?,
            bank_type = ?,
            payer_openid = COALESCE(NULLIF(?, ''), payer_openid),
            payer_total = ?,
            paid_at = CASE WHEN ? = 'SUCCESS' THEN NULLIF(?, '')::timestamptz ELSE paid_at END,
            notify_payload_json = CAST(? AS jsonb),
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (
            status,
            trade_state,
            _normalized_text(transaction.get("transaction_id")),
            _normalized_text(transaction.get("bank_type")),
            _normalized_text(payer.get("openid")),
            int(amount.get("payer_total") or amount.get("total") or 0),
            trade_state,
            _normalized_text(transaction.get("success_time")),
            _json(transaction),
            out_trade_no,
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_event(
    *,
    out_trade_no: str,
    event_type: str,
    transaction_id: str = "",
    trade_state: str = "",
    payload: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_order_events (
            out_trade_no,
            event_type,
            transaction_id,
            trade_state,
            payload_json,
            headers_json,
            created_at
        )
        VALUES (?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(out_trade_no),
            _normalized_text(event_type),
            _normalized_text(transaction_id),
            _normalized_text(trade_state),
            _json(payload or {}),
            _json(headers or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}
