#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import dump_json, ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from script_runtime import dump_json, ensure_repo_root_on_path, print_json


ROOT = ensure_repo_root_on_path()
DEFAULT_ORDER_ID = "156"

EXPECTED_PAYMENT_CONSUMERS = (
    "order_projection_consumer",
    "webhook_order_paid_consumer",
    "automation_payment_consumer",
    "customer_business_summary_consumer",
    "dnd_policy_consumer",
    "ai_assist_notify_consumer",
)

PAYMENT_PLACEHOLDER_CONSUMERS: tuple[str, ...] = ()

INTERNAL_EVENT_CONSUMER_PENDING_REPAIR_DECISIONS = {
    "expected_not_applicable",
    "scheduler_not_running",
    "run_due_not_executed",
    "consumer_disabled_by_config",
    "consumer_placeholder_only",
    "retry_replay_available",
    "runtime_repair_required",
    "operator_action_required",
    "unknown_requires_manual_review",
}

CUSTOMER_LINKAGE_REPAIR_DECISIONS = {
    "expected_not_applicable",
    "projection_missing",
    "customer_identity_missing",
    "channel_linkage_only",
    "backfill_required",
    "runtime_projection_repair_required",
    "operator_action_required",
    "unknown_requires_manual_review",
}

SENSITIVE_KEY_PARTS = (
    "authorization",
    "token",
    "secret",
    "corpsecret",
    "access_token",
    "external_userid",
    "external_user_id",
    "phone",
    "mobile",
    "openid",
    "unionid",
    "order_no",
)


def run(
    *,
    order_id: str = DEFAULT_ORDER_ID,
    input_json: Path | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    if input_json:
        evidence = json.loads(input_json.read_text(encoding="utf-8"))
        evidence.setdefault("source", {"type": "input_json", "path": str(input_json)})
    else:
        evidence = _load_readonly_db_evidence(order_id=order_id, database_url=database_url)
    return classify_evidence(evidence)


def classify_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    evidence = _redact_payload(evidence)
    internal_event = _classify_internal_event(evidence)
    external_effect = _classify_external_effect_linkage(evidence)
    linkage = _classify_order_customer_channel_linkage(evidence)
    internal_event_repair = _decide_internal_event_consumer_repair(internal_event, evidence)
    customer_linkage_repair = _decide_customer_linkage_repair(linkage, evidence)

    blocker_1 = internal_event["classification"]
    blocker_2 = linkage["classification"]
    runtime_fix_required = bool(internal_event_repair["next_pr_required"])
    data_backfill_required = bool(customer_linkage_repair["approved_backfill_runbook_required"])
    operator_action_required = (
        blocker_1 != "expected_not_applicable"
        or blocker_2 != "expected_not_applicable"
        or external_effect["classification"] != "expected_not_applicable"
    )
    can_recollect = not operator_action_required

    output = {
        "ok": True,
        "readonly": True,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
        "order_id": str(evidence.get("order_id") or DEFAULT_ORDER_ID),
        "source": evidence.get("source") or {"type": "fixture_or_diagnostic"},
        "internal_event": internal_event,
        "internal_event_consumer_pending_decision": internal_event_repair,
        "external_effect_linkage": external_effect,
        "order_customer_channel_linkage": linkage,
        "customer_read_model_linkage_decision": customer_linkage_repair,
        "conclusion": {
            "blocker_1_classification": blocker_1,
            "blocker_1_current_status": blocker_1,
            "blocker_1_repair_decision": internal_event_repair["repair_decision"],
            "blocker_1_next_pr_required": bool(internal_event_repair["next_pr_required"]),
            "blocker_2_classification": blocker_2,
            "blocker_2_current_status": blocker_2,
            "blocker_2_repair_decision": customer_linkage_repair["repair_decision"],
            "blocker_2_next_pr_required": bool(customer_linkage_repair["next_pr_required"]),
            "retryable": False,
            "operator_action_required": operator_action_required,
            "runtime_fix_required": runtime_fix_required,
            "data_backfill_required": data_backfill_required,
            "can_recollect_external_orders_evidence": can_recollect,
            "can_claim_external_orders_90_plus": False,
            "required_operator_actions": _required_operator_actions(internal_event_repair, customer_linkage_repair),
            "required_runtime_repairs": _required_runtime_repairs(internal_event_repair, customer_linkage_repair),
            "required_backfill_or_projection_repairs": _required_projection_repairs(customer_linkage_repair),
            "recommended_next_pr": _recommended_next_pr(blocker_1=blocker_1, blocker_2=blocker_2),
            "business_explanation": _business_explanation(
                internal_event=internal_event,
                external_effect=external_effect,
                linkage=linkage,
            ),
        },
        "sensitive_data_redaction_ok": True,
    }
    return _redact_payload(output)


def _decide_internal_event_consumer_repair(internal_event: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    pending = list(internal_event.get("pending_consumers") or [])
    failed = list(internal_event.get("failed_consumers") or [])
    missing = list(internal_event.get("missing_consumers") or [])
    actual_count = int(internal_event.get("actual_consumer_count") or 0)
    config = dict(evidence.get("internal_event_config") or {})
    all_pending_unattempted = bool(pending) and all(int(row.get("attempt_count") or 0) == 0 for row in pending)

    if internal_event.get("classification") == "expected_not_applicable":
        decision = "expected_not_applicable"
        next_pr_required = False
        reason = "All expected payment consumers are finished or intentionally skipped."
    elif missing or actual_count == 0:
        decision = "runtime_repair_required"
        next_pr_required = True
        reason = "Expected payment consumer run rows are missing."
    elif failed:
        decision = "retry_replay_available"
        next_pr_required = True
        reason = "At least one consumer has failed; retry/replay routes exist but require approved operator action."
    elif all_pending_unattempted:
        decision = "run_due_not_executed"
        next_pr_required = True
        reason = "All pending consumers have attempt_count=0 and no recorded error, so the due worker has not processed this event."
    elif pending:
        decision = "unknown_requires_manual_review"
        next_pr_required = True
        reason = "Pending consumers exist, but their attempt history is not sufficient to classify automatically."
    else:
        decision = "unknown_requires_manual_review"
        next_pr_required = True
        reason = "Internal event state is not recognized by the repair decision classifier."

    assert decision in INTERNAL_EVENT_CONSUMER_PENDING_REPAIR_DECISIONS
    return {
        "repair_decision": decision,
        "current_status": internal_event.get("classification"),
        "expected_consumer_names": list(EXPECTED_PAYMENT_CONSUMERS),
        "actual_consumer_run_count": actual_count,
        "pending_consumer_names": [row.get("consumer_name") for row in pending],
        "failed_consumer_names": [row.get("consumer_name") for row in failed],
        "missing_consumer_names": missing,
        "why_attempt_count_zero": reason if all_pending_unattempted else "",
        "run_due_route_available": True,
        "run_due_preview_route": "/api/admin/internal-events/run-due/preview",
        "run_due_execute_route": "/api/admin/internal-events/run-due",
        "single_consumer_run_route": "/api/admin/internal-events/{event_id}/consumers/{consumer_name}/run",
        "retry_route_available": True,
        "retry_route": "/api/admin/internal-events/{event_id}/consumers/{consumer_name}/retry",
        "skip_route_available": True,
        "skip_route": "/api/admin/internal-events/{event_id}/consumers/{consumer_name}/skip",
        "non_dry_run_requires_internal_token": True,
        "non_dry_run_requires_auto_execute_gate": True,
        "non_dry_run_requires_event_consumer_allowlist": True,
        "consumer_disabled_by_config": bool(config.get("internal_events_enabled") is False or config.get("payment_internal_events_enabled") is False),
        "consumer_placeholder_only": False,
        "shadow_only_semantics": bool(config.get("shadow_only")) if "shadow_only" in config else "not_collected",
        "not_applicable_semantics": False,
        "can_mark_expected_not_applicable": False,
        "must_remain_blocking": decision != "expected_not_applicable",
        "operator_action_required": decision != "expected_not_applicable",
        "next_pr_required": next_pr_required,
        "recommended_operator_action": (
            "Preview the single payment.succeeded event and execute only approved batch-size-one consumers during an operator window."
            if decision == "run_due_not_executed"
            else "Review internal event consumer state before recollecting External Orders evidence."
        ),
    }


def _decide_customer_linkage_repair(linkage: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    external_userid_present = bool(linkage.get("external_userid_present"))
    channel_present = linkage.get("channel_contact_linkage_evidence") == "present"
    customer_list_rows = int(linkage.get("customer_list_index_next_rows") or 0)
    detail_rows = int(linkage.get("customer_detail_snapshot_next_rows") or 0)

    if not external_userid_present:
        decision = "customer_identity_missing"
        next_pr_required = True
        reason = "The order has no usable redacted external customer identity evidence."
    elif customer_list_rows > 0 or detail_rows > 0:
        decision = "expected_not_applicable"
        next_pr_required = False
        reason = "Customer read model linkage is present."
    elif channel_present:
        decision = "runtime_projection_repair_required"
        next_pr_required = True
        reason = (
            "The order has redacted customer identity and channel contact evidence, but the customer read model "
            "projection has no linked row. Current customer read-model sources do not make order/channel-contact "
            "linkage sufficient by themselves."
        )
    else:
        decision = "channel_linkage_only"
        next_pr_required = True
        reason = "Customer identity exists but channel/customer projection evidence is incomplete."

    assert decision in CUSTOMER_LINKAGE_REPAIR_DECISIONS
    return {
        "repair_decision": decision,
        "current_status": linkage.get("classification"),
        "customer_identity_evidence": linkage.get("redacted_customer_identifier_evidence"),
        "channel_contact_linkage_evidence": linkage.get("channel_contact_linkage_evidence"),
        "customer_list_index_next_lookup_result": customer_list_rows,
        "customer_detail_snapshot_next_lookup_result": detail_rows,
        "projectable_identity_fields_present": external_userid_present or channel_present,
        "projection_should_link_order": external_userid_present and channel_present,
        "existing_backfill_script": "scripts/backfill_customer_read_model.py",
        "existing_backfill_production_safe_by_default": True,
        "existing_backfill_writes_only_with_execute_and_approved_target": True,
        "existing_projection_sources_note": (
            "Customer read model live source is based on customer/contact identity sources; this triage did not find "
            "a completed customer read-model row for the order's redacted identity."
        ),
        "approved_backfill_runbook_required": decision in {"backfill_required", "runtime_projection_repair_required"},
        "operator_action_required": decision != "expected_not_applicable",
        "next_pr_required": next_pr_required,
        "recommended_operator_action": reason,
    }


def _classify_internal_event(evidence: dict[str, Any]) -> dict[str, Any]:
    event = evidence.get("internal_event") or {}
    runs = evidence.get("consumer_runs") or event.get("consumer_runs") or []
    event_exists = bool(event.get("exists", event))
    consumer_names = {str(row.get("consumer_name") or row.get("consumer") or "") for row in runs}
    missing_consumers = [name for name in EXPECTED_PAYMENT_CONSUMERS if name not in consumer_names]
    pending = [
        {
            "consumer_name": str(row.get("consumer_name") or row.get("consumer") or ""),
            "status": str(row.get("status") or ""),
            "attempt_count": int(row.get("attempt_count") or 0),
            "pending_reason": _pending_reason(row),
        }
        for row in runs
        if str(row.get("status") or "").lower() == "pending"
    ]
    failed = [
        {
            "consumer_name": str(row.get("consumer_name") or row.get("consumer") or ""),
            "status": str(row.get("status") or ""),
            "error_code": str(row.get("error_code") or row.get("last_error_code") or ""),
            "error_message": str(row.get("error_message") or row.get("last_error_message") or ""),
        }
        for row in runs
        if str(row.get("status") or "").lower() in {"failed", "error"}
    ]

    if not event_exists:
        classification = "projection_missing"
        blocking = ["missing_internal_event"]
    elif missing_consumers:
        classification = "consumer_not_registered"
        blocking = ["missing_expected_consumer_run"]
    elif pending:
        classification = "consumer_run_pending_due_to_config"
        blocking = ["consumer_pending"]
    elif failed:
        classification = "runtime_bug"
        blocking = ["consumer_failed"]
    else:
        classification = "expected_not_applicable"
        blocking = []

    return {
        "event_type": event.get("event_type") or "not_found",
        "event_id": event.get("event_id") or "not_found",
        "aggregate_type": event.get("aggregate_type") or "not_found",
        "aggregate_id": str(event.get("aggregate_id") or event.get("order_id") or "not_found"),
        "expected_consumers": list(EXPECTED_PAYMENT_CONSUMERS),
        "actual_consumer_count": len(runs),
        "missing_consumers": missing_consumers,
        "pending_consumers": pending,
        "failed_consumers": failed,
        "classification": classification,
        "blocking_reasons": blocking,
        "pending_is_blocking": bool(pending or missing_consumers or failed or not event_exists),
    }


def _classify_external_effect_linkage(evidence: dict[str, Any]) -> dict[str, Any]:
    effect = evidence.get("external_effect_linkage") or {}
    jobs = effect.get("jobs") or effect.get("external_effect_jobs") or []
    attempts = effect.get("attempts") or effect.get("external_effect_attempts") or []
    push_center_status = effect.get("push_center_status") or effect.get("effective_status") or ""
    failed_attempts = [
        row
        for row in attempts
        if str(row.get("status") or row.get("raw_status") or "").lower() not in {"succeeded", "sent"}
    ]

    if not jobs:
        classification = "projection_missing"
        blocking = ["missing_external_effect_job"]
    elif not attempts:
        classification = "projection_missing"
        blocking = ["missing_external_effect_attempt"]
    elif failed_attempts:
        classification = "requires_operator_action"
        blocking = ["external_effect_attempt_not_succeeded"]
    elif push_center_status and push_center_status not in {"sent", "succeeded"}:
        classification = "requires_operator_action"
        blocking = ["push_center_not_sent"]
    else:
        classification = "expected_not_applicable"
        blocking = []

    return {
        "effect_job_count": len(jobs),
        "attempt_count": len(attempts),
        "attempt_statuses": sorted({str(row.get("status") or row.get("raw_status") or "") for row in attempts}),
        "push_center_visibility": bool(push_center_status),
        "push_center_status": push_center_status or "not_found",
        "classification": classification,
        "blocking_reasons": blocking,
    }


def _classify_order_customer_channel_linkage(evidence: dict[str, Any]) -> dict[str, Any]:
    linkage = evidence.get("order_customer_channel_linkage") or {}
    external_userid_present = bool(linkage.get("external_userid_present"))
    customer_rows = int(linkage.get("customer_list_index_rows") or linkage.get("customer_index_rows") or 0)
    detail_rows = int(linkage.get("customer_detail_snapshot_rows") or 0)
    channel_rows = int(linkage.get("channel_contact_rows") or 0)
    channel_ids_present = int(linkage.get("channel_ids_present") or 0)

    if not external_userid_present:
        classification = "expected_not_applicable"
        blocking = []
        repair_required = False
    elif customer_rows <= 0 and detail_rows <= 0:
        classification = "linkage_missing"
        blocking = ["missing_customer_read_model_linkage"]
        repair_required = True
    elif channel_rows <= 0 and channel_ids_present <= 0:
        classification = "linkage_missing"
        blocking = ["missing_channel_contact_linkage"]
        repair_required = True
    else:
        classification = "expected_not_applicable"
        blocking = []
        repair_required = False

    return {
        "order_id": str(linkage.get("order_id") or evidence.get("order_id") or DEFAULT_ORDER_ID),
        "provider": linkage.get("provider") or "wechat_pay",
        "source": linkage.get("source") or "not_collected",
        "external_userid_present": external_userid_present,
        "redacted_customer_identifier_evidence": linkage.get("redacted_customer_identifier_evidence")
        or ("present_redacted" if external_userid_present else "not_present"),
        "channel_contact_linkage_evidence": "present" if channel_rows > 0 or channel_ids_present > 0 else "missing",
        "customer_list_index_next_rows": customer_rows,
        "customer_detail_snapshot_next_rows": detail_rows,
        "classification": classification,
        "blocking_reasons": blocking,
        "data_backfill_required": repair_required,
    }


def _pending_reason(row: dict[str, Any]) -> str:
    reason = row.get("pending_reason") or row.get("reason")
    if reason:
        return str(reason)
    if int(row.get("attempt_count") or 0) == 0 and not row.get("last_error_code") and not row.get("error_code"):
        return "run_not_started_no_error_recorded"
    return "pending_reason_not_recorded"


def _recommended_next_pr(*, blocker_1: str, blocker_2: str) -> str:
    if blocker_1 in {"projection_missing", "consumer_not_registered", "consumer_run_pending_due_to_config", "runtime_bug"}:
        if blocker_2 in {"data_backfill_missing", "linkage_missing", "projection_missing"}:
            return "consumer pending classification/repair plus customer read-model linkage projection/backfill triage"
        return "consumer pending classification/repair"
    if blocker_2 in {"data_backfill_missing", "linkage_missing", "projection_missing"}:
        return "customer read-model linkage projection/backfill triage"
    return "external orders evidence recollection"


def _required_operator_actions(internal_event_repair: dict[str, Any], customer_linkage_repair: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if internal_event_repair.get("repair_decision") == "run_due_not_executed":
        actions.append("preview and execute approved payment.succeeded consumers one at a time during an operator window")
    elif internal_event_repair.get("operator_action_required"):
        actions.append("review internal event consumer state and classify pending runs")
    if customer_linkage_repair.get("operator_action_required"):
        actions.append("confirm whether customer read-model linkage should exist for this order/customer identity")
    return actions


def _required_runtime_repairs(internal_event_repair: dict[str, Any], customer_linkage_repair: dict[str, Any]) -> list[str]:
    repairs: list[str] = []
    if internal_event_repair.get("repair_decision") in {"runtime_repair_required", "scheduler_not_running"}:
        repairs.append("repair internal event consumer registration or scheduler/run-due configuration")
    if customer_linkage_repair.get("repair_decision") == "runtime_projection_repair_required":
        repairs.append("repair customer read-model projection so payment order customer identity can link to customer list/detail")
    return repairs


def _required_projection_repairs(customer_linkage_repair: dict[str, Any]) -> list[str]:
    if customer_linkage_repair.get("repair_decision") in {"backfill_required", "runtime_projection_repair_required"}:
        return ["approved customer read-model projection/backfill repair path required before External Orders 90%+ recollection"]
    return []


def _business_explanation(
    *,
    internal_event: dict[str, Any],
    external_effect: dict[str, Any],
    linkage: dict[str, Any],
) -> str:
    parts: list[str] = []
    if external_effect["classification"] == "expected_not_applicable":
        parts.append("External order push evidence is linked and no retry is needed.")
    else:
        parts.append("External order push evidence is incomplete or requires operator action.")
    if internal_event["classification"] == "consumer_run_pending_due_to_config":
        parts.append("Internal event consumers are still pending with no recorded attempts.")
    elif internal_event["classification"] != "expected_not_applicable":
        parts.append(f"Internal event blocker classified as {internal_event['classification']}.")
    if linkage["classification"] == "linkage_missing":
        parts.append("Order has channel evidence but customer read-model linkage is missing.")
    elif linkage["classification"] != "expected_not_applicable":
        parts.append(f"Customer/channel linkage blocker classified as {linkage['classification']}.")
    if len(parts) == 1:
        parts.append("External Orders evidence can be recollected for 90%+ review.")
    return " ".join(parts)


def _load_readonly_db_evidence(*, order_id: str, database_url: str | None) -> dict[str, Any]:
    database_url = database_url or os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return {
            "order_id": str(order_id),
            "source": {"type": "database", "status": "unavailable", "reason": "DATABASE_URL not configured"},
            "internal_event": {"exists": False, "event_type": "not_collected"},
            "consumer_runs": [],
            "external_effect_linkage": {"jobs": [], "attempts": [], "push_center_status": ""},
            "order_customer_channel_linkage": {"order_id": str(order_id)},
        }

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - depends on local optional package
        return {
            "order_id": str(order_id),
            "source": {"type": "database", "status": "unavailable", "reason": f"psycopg import failed: {exc}"},
            "internal_event": {"exists": False, "event_type": "not_collected"},
            "consumer_runs": [],
            "external_effect_linkage": {"jobs": [], "attempts": [], "push_center_status": ""},
            "order_customer_channel_linkage": {"order_id": str(order_id)},
        }

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        conn.execute("BEGIN READ ONLY")
        order_row = conn.execute(
            """
            select id, provider, order_source as source,
                   coalesce(external_userid, '') <> '' as external_userid_present
              from wechat_pay_orders
             where id = %s
            """,
            (order_id,),
        ).fetchone() or {}
        event_row = conn.execute(
            """
            select id, event_id, event_type, aggregate_type, aggregate_id, source_module, source_route
              from internal_event
             where event_type = 'payment.succeeded'
               and aggregate_id = %s
             order by created_at desc
             limit 1
            """,
            (str(order_id),),
        ).fetchone() or {}
        consumer_runs = []
        if event_row:
            consumer_runs = conn.execute(
                """
                select consumer_name, status, attempt_count, last_error_code, last_error_message
                  from internal_event_consumer_run
                 where event_id = %s
                 order by consumer_name
                """,
                (event_row["event_id"],),
            ).fetchall()
        jobs = conn.execute(
            """
            select id, raw_status as status, execution_mode, effect_type, last_error_code, last_error_message
              from external_effect_job
             where business_type = 'commerce_order'
               and business_id = %s
             order by id desc
            """,
            (str(order_id),),
        ).fetchall()
        job_ids = [row["id"] for row in jobs]
        attempts = []
        if job_ids:
            attempts = conn.execute(
                """
                select id, attempt_id, job_id, raw_status, status, adapter_mode, error_code, error_message
                  from external_effect_attempt
                 where job_id = any(%s)
                 order by id desc
                """,
                (job_ids,),
            ).fetchall()
        customer_rows = conn.execute(
            """
            select count(*)::int as count
              from customer_list_index_next
             where order_ids @> to_jsonb(array[%s]::int[])
            """,
            (int(order_id),),
        ).fetchone()
        channel_rows = conn.execute(
            """
            select count(*)::int as count,
                   count(distinct channel_id)::int as channel_ids_present
              from automation_channel_contact
             where external_userid = (
                   select external_userid
                     from wechat_pay_orders
                    where id = %s
                  )
            """,
            (order_id,),
        ).fetchone() or {}
        conn.execute("ROLLBACK")

    return _redact_payload(
        {
            "order_id": str(order_id),
            "source": {"type": "database", "status": "readonly_collected"},
            "internal_event": {
                "exists": bool(event_row),
                "event_id": _redact_id(str(event_row.get("event_id") or "")),
                "event_type": event_row.get("event_type") or "not_found",
                "aggregate_type": event_row.get("aggregate_type") or "not_found",
                "aggregate_id": str(event_row.get("aggregate_id") or "not_found"),
                "source_module": event_row.get("source_module") or "not_found",
                "source_route": event_row.get("source_route") or "not_found",
            },
            "consumer_runs": consumer_runs,
            "external_effect_linkage": {
                "jobs": jobs,
                "attempts": attempts,
                "push_center_status": "sent" if jobs and all(row.get("status") == "succeeded" for row in jobs) else "",
            },
            "order_customer_channel_linkage": {
                "order_id": str(order_id),
                "provider": order_row.get("provider") or "not_found",
                "source": order_row.get("source") or "not_found",
                "external_userid_present": bool(order_row.get("external_userid_present")),
                "customer_list_index_rows": int((customer_rows or {}).get("count") or 0),
                "customer_detail_snapshot_rows": 0,
                "channel_contact_rows": int(channel_rows.get("count") or 0),
                "channel_ids_present": int(channel_rows.get("channel_ids_present") or 0),
            },
        }
    )


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                if isinstance(item, bool):
                    redacted[key] = item
                elif key in {"external_userid_present", "token_configured"}:
                    redacted[key] = bool(item)
                else:
                    redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, str) and value.startswith("iev_"):
        return _redact_id(value)
    return value


def _redact_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Readonly triage for External Orders 90%+ evidence blockers."
    )
    parser.add_argument("--order-id", default=DEFAULT_ORDER_ID, help="Internal order id to inspect. Default: 156")
    parser.add_argument("--input-json", type=Path, help="Classify a redacted evidence JSON fixture instead of DB.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional database URL. Defaults to DATABASE_URL. Used only for readonly SELECT diagnostics.",
    )
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation. Use 0 for compact output.")
    args = parser.parse_args(argv)

    payload = run(order_id=args.order_id, input_json=args.input_json, database_url=args.database_url)
    print_json(payload, indent=None if args.indent == 0 else args.indent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
