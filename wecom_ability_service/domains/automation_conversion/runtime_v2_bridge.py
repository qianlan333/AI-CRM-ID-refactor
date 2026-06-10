from __future__ import annotations

from typing import Any

from ...db import get_db
from aicrm_next.automation_runtime_v2 import process_event
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput, EVENT_CHANNEL_ENTERED, EVENT_PAYMENT_SUCCEEDED, EVENT_QUESTIONNAIRE_SUBMITTED, text
from aicrm_next.automation_runtime_v2.event_store import get_event, insert_event, mark_ignored


def _row(row: Any) -> dict[str, Any]:
    return dict(row or {})


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


def process_binding_import(
    *,
    program_id: int,
    binding: dict[str, Any],
    batch_size: int = 500,
    max_import_count: int | None = 1000,
) -> dict[str, Any]:
    channel_id = int(binding.get("channel_id") or 0)
    binding_id = int(binding.get("id") or 0)
    limit = max(1, int(batch_size or 500))
    offset = 0
    total_contact_count = int(
        (
            get_db()
            .execute(
                "SELECT COUNT(*) AS count FROM automation_channel_contact WHERE channel_id = ?",
                (channel_id,),
            )
            .fetchone()
            or {}
        )["count"]
        or 0
    )
    if max_import_count is not None and int(max_import_count or 0) > 0 and total_contact_count > int(max_import_count):
        return {
            "history_imported": False,
            "requires_batch_import": True,
            "total_contact_count": total_contact_count,
            "max_import_count": int(max_import_count),
            "import_continue_token": f"{int(program_id)}:{binding_id}:0",
            "imported_contact_count": 0,
            "skipped_existing_count": 0,
            "failed_count": 0,
            "generated_event_count": 0,
            "generated_membership_count": 0,
            "generated_stage_entry_count": 0,
            "generated_task_plan_count": 0,
            "generated_broadcast_job_count": 0,
            "runtime_v2_summary": [],
        }
    summary = {
        "history_imported": True,
        "requires_batch_import": False,
        "total_contact_count": total_contact_count,
        "imported_contact_count": 0,
        "skipped_existing_count": 0,
        "failed_count": 0,
        "generated_event_count": 0,
        "generated_membership_count": 0,
        "generated_stage_entry_count": 0,
        "generated_task_plan_count": 0,
        "generated_broadcast_job_count": 0,
        "runtime_v2_summary": [],
    }
    while True:
        contacts = get_db().execute(
            """
            SELECT *
            FROM automation_channel_contact
            WHERE channel_id = ?
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (channel_id, limit, offset),
        ).fetchall()
        if not contacts:
            break
        for raw in contacts:
            contact = dict(raw)
            contact_id = int(contact.get("id") or 0)
            source_id = f"{int(program_id)}:{binding_id}:{contact_id}"
            existing = get_db().execute(
                "SELECT id FROM automation_event_v2 WHERE source_type = 'binding_import' AND source_id = ? LIMIT 1",
                (source_id,),
            ).fetchone()
            try:
                event = insert_event(
                    AutomationEventInput(
                        event_type=EVENT_CHANNEL_ENTERED,
                        source_type="binding_import",
                        source_id=source_id,
                        idempotency_key=f"binding_import:{int(program_id)}:{binding_id}:{contact_id}",
                        program_id=int(program_id),
                        channel_id=channel_id,
                        binding_id=binding_id,
                        external_userid=text(contact.get("external_contact_id")),
                        person_id=int(contact.get("master_customer_id") or 0) or None,
                        occurred_at=binding.get("bound_at"),
                        raw_occurred_at=contact.get("first_channel_entered_at"),
                        payload_json={"binding_id": binding_id, "channel_contact_id": contact_id, "import_source": "channel_binding_history"},
                    )
                )
                result = process_event(int(event["id"]))
                summary["imported_contact_count"] += 1
                summary["generated_event_count"] += 0 if existing else 1
                summary["skipped_existing_count"] += 1 if existing else 0
                summary["generated_membership_count"] += 1 if (result.get("membership") or {}).get("id") else 0
                summary["generated_stage_entry_count"] += 1 if result.get("stage_entry") else 0
                summary["generated_task_plan_count"] += int((result.get("counts") or {}).get("planned") or 0)
                summary["generated_broadcast_job_count"] += int((result.get("counts") or {}).get("enqueued") or 0)
                summary["runtime_v2_summary"].append({"event_id": int(event["id"]), "result": result.get("counts") or {}})
            except Exception as exc:
                try:
                    get_db().rollback()
                except Exception:
                    pass
                summary["failed_count"] += 1
                summary["runtime_v2_summary"].append({"source_id": source_id, "error": str(exc)})
        if len(contacts) < limit:
            break
        offset += limit
    return summary


def process_channel_entry_event(
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


def process_questionnaire_submission_event(
    *,
    external_userid: str = "",
    phone: str = "",
    questionnaire_id: int | None = None,
    submission_id: int | None = None,
    payload_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_id = str(submission_id or text((payload_json or {}).get("submission_id")))
    event = insert_event(
        AutomationEventInput(
            event_type=EVENT_QUESTIONNAIRE_SUBMITTED,
            source_type="questionnaire",
            source_id=source_id,
            idempotency_key=f"questionnaire:{source_id}",
            external_userid=text(external_userid),
            phone=text(phone),
            payload_json={"questionnaire_id": questionnaire_id, "submission_id": submission_id, **dict(payload_json or {})},
        )
    )
    return process_event(int(event["id"]))


def process_payment_succeeded_event(*, order: dict[str, Any], transaction: dict[str, Any] | None = None) -> dict[str, Any]:
    order_id = text(order.get("out_trade_no") or order.get("id") or (transaction or {}).get("out_trade_no"))
    event = insert_event(
        AutomationEventInput(
            event_type=EVENT_PAYMENT_SUCCEEDED,
            source_type="payment",
            source_id=order_id,
            idempotency_key=f"payment:{order_id}",
            external_userid=text(order.get("external_userid") or order.get("userid_snapshot")),
            phone=text(order.get("mobile_snapshot") or order.get("respondent_key")),
            payload_json={
                "order_id": order_id,
                "product_id": order.get("product_id") or order.get("product_code"),
                "amount": order.get("amount_total") or order.get("payer_total"),
                "paid_at": order.get("paid_at"),
                "transaction": dict(transaction or {}),
            },
        )
    )
    return process_event(int(event["id"]))
