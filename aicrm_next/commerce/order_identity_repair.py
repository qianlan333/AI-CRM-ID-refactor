from __future__ import annotations

import json
from typing import Any

from aicrm_next.public_product.repo import connect_h5_wechat_pay_db


DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BATCH_LIMIT = 100


def _text(value: Any) -> str:
    return str(value or "").strip()


def _jsonb(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _int(value: Any, *, default: int = 0, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def _paid_order_clause() -> str:
    return """
        (o.status = 'paid' OR o.trade_state = 'SUCCESS')
        AND NOT (
            COALESCE(o.refund_status, '') = 'full_refunded'
            OR (o.amount_total > 0 AND COALESCE(o.refunded_amount_total, 0) >= o.amount_total)
        )
    """


def fetch_missing_order_identity_candidates(
    conn: Any,
    *,
    limit: int = DEFAULT_BATCH_LIMIT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            o.id,
            o.out_trade_no,
            o.product_code,
            o.product_name,
            o.unionid,
            o.payer_openid,
            o.mobile_snapshot,
            o.external_userid,
            o.userid_snapshot,
            o.paid_at,
            COALESCE(r.attempt_count, 0) AS repair_attempt_count,
            COALESCE(r.status, 'pending') AS repair_status
        FROM wechat_pay_orders o
        LEFT JOIN wechat_pay_order_identity_repair r ON r.order_id = o.id
        WHERE COALESCE(o.external_userid, '') = ''
          AND ({_paid_order_clause()})
          AND (
            COALESCE(o.unionid, '') <> ''
            OR COALESCE(o.payer_openid, '') <> ''
            OR COALESCE(o.mobile_snapshot, '') <> ''
          )
          AND (
            r.order_id IS NULL
            OR (
              r.status IN ('pending', 'retryable')
              AND r.attempt_count < %s
              AND (r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)
            )
          )
        ORDER BY o.paid_at ASC NULLS LAST, o.id ASC
        LIMIT %s
        FOR UPDATE OF o SKIP LOCKED
        """,
        (max_attempts, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_order_identity(conn: Any, order: dict[str, Any]) -> dict[str, str]:
    lookup_plan = [
        ("unionid", _text(order.get("unionid")), "unionid"),
        ("openid", _text(order.get("payer_openid")), "openid"),
    ]
    for field, value, matched_by in lookup_plan:
        if not value:
            continue
        row = conn.execute(
            f"""
            SELECT external_userid, follow_user_userid AS owner_userid
            FROM wecom_external_contact_identity_map
            WHERE {field} = %s
              AND COALESCE(external_userid, '') <> ''
            ORDER BY
              CASE WHEN COALESCE(status, '') IN ('active', 'following', '') THEN 0 ELSE 1 END,
              updated_at DESC NULLS LAST,
              id DESC
            LIMIT 1
            """,
            (value,),
        ).fetchone()
        if row and _text(row.get("external_userid")):
            return {
                "external_userid": _text(row.get("external_userid")),
                "owner_userid": _text(row.get("owner_userid")),
                "matched_by": matched_by,
            }

    mobile = _text(order.get("mobile_snapshot"))
    if mobile:
        row = conn.execute(
            """
            SELECT b.external_userid, b.last_owner_userid AS owner_userid
            FROM people p
            JOIN external_contact_bindings b ON b.person_id::text = p.id::text
            WHERE p.mobile = %s
              AND COALESCE(b.external_userid, '') <> ''
            ORDER BY b.updated_at DESC NULLS LAST, b.external_userid DESC
            LIMIT 1
            """,
            (mobile,),
        ).fetchone()
        if row and _text(row.get("external_userid")):
            return {
                "external_userid": _text(row.get("external_userid")),
                "owner_userid": _text(row.get("owner_userid")),
                "matched_by": "mobile",
            }

    return {}


def _ensure_repair_row(conn: Any, order: dict[str, Any], *, max_attempts: int) -> None:
    conn.execute(
        """
        INSERT INTO wechat_pay_order_identity_repair (
            order_id, out_trade_no, status, max_attempts, created_at, updated_at
        )
        VALUES (%s, %s, 'pending', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (order_id) DO UPDATE SET
            out_trade_no = EXCLUDED.out_trade_no,
            max_attempts = EXCLUDED.max_attempts,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(order["id"]), _text(order.get("out_trade_no")), max_attempts),
    )


def _mark_repair_succeeded(conn: Any, order: dict[str, Any], resolved: dict[str, str]) -> None:
    detail = {
        "matched_by": resolved["matched_by"],
        "source": "wechat_pay_order_identity_repair",
        "order_id": int(order["id"]),
    }
    conn.execute(
        """
        UPDATE wechat_pay_orders
        SET external_userid = %s,
            userid_snapshot = CASE
                WHEN COALESCE(userid_snapshot, '') = '' THEN %s
                ELSE userid_snapshot
            END,
            metadata_json = jsonb_set(
                COALESCE(metadata_json, '{}'::jsonb),
                '{identity_repair}',
                %s::jsonb,
                TRUE
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND COALESCE(external_userid, '') = ''
        """,
        (
            resolved["external_userid"],
            resolved.get("owner_userid", ""),
            _jsonb(detail),
            int(order["id"]),
        ),
    )
    conn.execute(
        """
        UPDATE wechat_pay_order_identity_repair
        SET status = 'succeeded',
            attempt_count = attempt_count + 1,
            matched_by = %s,
            resolved_external_userid = %s,
            resolved_owner_userid = %s,
            last_error_code = '',
            last_error_message = '',
            last_attempted_at = CURRENT_TIMESTAMP,
            repaired_at = CURRENT_TIMESTAMP,
            next_retry_at = NULL,
            detail_json = %s::jsonb,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = %s
        """,
        (
            resolved["matched_by"],
            resolved["external_userid"],
            resolved.get("owner_userid", ""),
            _jsonb(detail),
            int(order["id"]),
        ),
    )


def _mark_repair_unresolved(conn: Any, order: dict[str, Any], *, max_attempts: int) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE wechat_pay_order_identity_repair
        SET attempt_count = attempt_count + 1,
            status = CASE WHEN attempt_count + 1 >= %s THEN 'exhausted' ELSE 'retryable' END,
            last_error_code = 'identity_not_found',
            last_error_message = 'No matching external_userid for order unionid/openid/mobile.',
            last_attempted_at = CURRENT_TIMESTAMP,
            next_retry_at = CASE WHEN attempt_count + 1 >= %s THEN NULL ELSE CURRENT_TIMESTAMP + INTERVAL '1 hour' END,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = %s
        RETURNING status, attempt_count
        """,
        (max_attempts, max_attempts, int(order["id"])),
    ).fetchone()
    return dict(row or {})


def repair_missing_order_identities(
    *,
    conn: Any | None = None,
    limit: int = DEFAULT_BATCH_LIMIT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    dry_run: bool = False,
) -> dict[str, Any]:
    effective_limit = _int(limit, default=DEFAULT_BATCH_LIMIT, minimum=1, maximum=1000)
    effective_max_attempts = _int(max_attempts, default=DEFAULT_MAX_ATTEMPTS, minimum=1, maximum=10)
    owns_connection = conn is None
    if conn is None:
        conn = connect_h5_wechat_pay_db()
    summary: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(dry_run),
        "scanned_count": 0,
        "repaired_count": 0,
        "retryable_count": 0,
        "exhausted_count": 0,
        "skipped_count": 0,
        "max_attempts": effective_max_attempts,
        "items": [],
        "real_external_call_executed": False,
    }
    try:
        candidates = fetch_missing_order_identity_candidates(
            conn,
            limit=effective_limit,
            max_attempts=effective_max_attempts,
        )
        summary["scanned_count"] = len(candidates)
        for order in candidates:
            item = {
                "order_id": int(order["id"]),
                "out_trade_no": _text(order.get("out_trade_no")),
                "product_code": _text(order.get("product_code")),
                "attempt_count_before": int(order.get("repair_attempt_count") or 0),
            }
            resolved = resolve_order_identity(conn, order)
            if dry_run:
                item["status"] = "would_repair" if resolved else "would_retry"
                item["matched_by"] = resolved.get("matched_by", "")
                summary["items"].append(item)
                continue
            _ensure_repair_row(conn, order, max_attempts=effective_max_attempts)
            if resolved:
                _mark_repair_succeeded(conn, order, resolved)
                summary["repaired_count"] += 1
                item.update(
                    {
                        "status": "succeeded",
                        "matched_by": resolved["matched_by"],
                        "external_userid": resolved["external_userid"],
                    }
                )
            else:
                state = _mark_repair_unresolved(conn, order, max_attempts=effective_max_attempts)
                status = _text(state.get("status")) or "retryable"
                if status == "exhausted":
                    summary["exhausted_count"] += 1
                else:
                    summary["retryable_count"] += 1
                item.update({"status": status, "error_code": "identity_not_found", "attempt_count_after": int(state.get("attempt_count") or 0)})
            summary["items"].append(item)
        if not dry_run and hasattr(conn, "commit"):
            conn.commit()
    except Exception:
        if not dry_run and hasattr(conn, "rollback"):
            conn.rollback()
        raise
    finally:
        if owns_connection and hasattr(conn, "close"):
            conn.close()
    summary["skipped_count"] = summary["scanned_count"] - summary["repaired_count"] - summary["retryable_count"] - summary["exhausted_count"]
    return summary
