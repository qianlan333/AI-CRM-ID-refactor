from __future__ import annotations

from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts, fetchone_dict


def get_profile_fields(external_userid: str) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        """
        SELECT external_userid, source, industry, industry_description,
               needs_blockers_followup, updated_by, updated_at
        FROM sidebar_customer_profile_fields
        WHERE external_userid = ?
        """,
        (str(external_userid or "").strip(),),
    )


def upsert_profile_fields(
    *,
    external_userid: str,
    source: str,
    industry: str,
    industry_description: str,
    needs_blockers_followup: str,
    updated_by: str,
) -> dict[str, Any]:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO sidebar_customer_profile_fields (
            external_userid, source, industry, industry_description,
            needs_blockers_followup, updated_by, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (external_userid) DO UPDATE SET
            source = EXCLUDED.source,
            industry = EXCLUDED.industry,
            industry_description = EXCLUDED.industry_description,
            needs_blockers_followup = EXCLUDED.needs_blockers_followup,
            updated_by = EXCLUDED.updated_by,
            updated_at = CURRENT_TIMESTAMP
        RETURNING external_userid, source, industry, industry_description,
                  needs_blockers_followup, updated_by, updated_at
        """,
        (
            str(external_userid or "").strip(),
            source,
            industry,
            industry_description,
            needs_blockers_followup,
            updated_by,
        ),
    ).fetchone()
    db.commit()
    return dict(row or {})


def get_workflow_title_for_customer(external_userid: str) -> str:
    row = fetchone_dict(
        get_db(),
        """
        SELECT COALESCE(NULLIF(w.workflow_name, ''), NULLIF(p.program_name, ''), NULLIF(c.channel_name, '')) AS title
        FROM automation_member m
        LEFT JOIN automation_channel c ON c.id = m.source_channel_id
        LEFT JOIN automation_program p ON p.id = c.program_id
        LEFT JOIN wecom_customer_acquisition_links l ON l.automation_channel_id = c.id
        LEFT JOIN automation_workflow w ON w.id = l.workflow_id
        WHERE m.external_contact_id = ?
        ORDER BY m.updated_at DESC, m.id DESC
        LIMIT 1
        """,
        (str(external_userid or "").strip(),),
    )
    return str((row or {}).get("title") or "").strip()


def list_customer_wechat_pay_orders(
    *,
    external_userid: str,
    mobile: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    identity_clauses: list[str] = []
    params: list[Any] = []
    if normalized_external_userid:
        identity_clauses.append("external_userid = ?")
        params.append(normalized_external_userid)
    if normalized_mobile:
        identity_clauses.append("mobile_snapshot = ?")
        params.append(normalized_mobile)
    if not identity_clauses:
        return []
    params.append(max(1, min(int(limit or 20), 100)))
    return fetchall_dicts(
        get_db(),
        f"""
        SELECT
            id,
            out_trade_no,
            product_code,
            COALESCE(NULLIF(product_name, ''), product_code) AS product_name,
            amount_total,
            currency,
            status,
            trade_state,
            refunded_amount_total,
            refund_status,
            paid_at,
            created_at
        FROM wechat_pay_orders
        WHERE ({" OR ".join(identity_clauses)})
        ORDER BY COALESCE(paid_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )
