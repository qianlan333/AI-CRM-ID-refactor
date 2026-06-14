from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_ORDER_PAID_PUSH
from aicrm_next.shared.runtime import production_data_ready, raw_database_url

from .consumer_registry import DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY, InternalEventConsumerRegistry
from .models import InternalEvent, InternalEventConsumerResult, InternalEventConsumerRun

PAYMENT_SUCCEEDED_EVENT_TYPE = "payment.succeeded"
TRANSACTION_PAID_EVENT_ALIAS = "transaction.paid"
PAYMENT_SUCCEEDED_EVENT_ALIAS = "payment_succeeded"
PAYMENT_SUCCEEDED_EVENT_TYPES = (
    PAYMENT_SUCCEEDED_EVENT_TYPE,
    TRANSACTION_PAID_EVENT_ALIAS,
    PAYMENT_SUCCEEDED_EVENT_ALIAS,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _order_from_event(event: InternalEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    return dict(order or {})


def _read_order_from_db(event: InternalEvent) -> dict[str, Any]:
    if not production_data_ready():
        return {}
    lookup = _text((event.payload_json or {}).get("order", {}).get("out_trade_no") if isinstance((event.payload_json or {}).get("order"), dict) else "")
    aggregate_id = _text(event.aggregate_id)
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(raw_database_url(), row_factory=dict_row) as conn:
            if lookup:
                row = conn.execute("SELECT * FROM wechat_pay_orders WHERE out_trade_no = %s LIMIT 1", (lookup,)).fetchone()
                if row:
                    return dict(row)
            if aggregate_id:
                row = conn.execute("SELECT * FROM wechat_pay_orders WHERE id::text = %s OR out_trade_no = %s LIMIT 1", (aggregate_id, aggregate_id)).fetchone()
                if row:
                    return dict(row)
    except Exception:
        return {}
    return {}


def _transaction_from_event(event: InternalEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    transaction = payload.get("transaction") if isinstance(payload.get("transaction"), dict) else {}
    return dict(transaction or {})


def _is_order_paid(order: dict[str, Any]) -> bool:
    return _text(order.get("status")) == "paid" or _text(order.get("trade_state")) == "SUCCESS"


def order_projection_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    order = _read_order_from_db(event) or _order_from_event(event)
    out_trade_no = _text(order.get("out_trade_no") or event.aggregate_id)
    if not order:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "aggregate_id": event.aggregate_id},
            response_summary={"order_found": False},
            error_code="order_payload_missing",
            error_message="payment.succeeded event is missing the order payload",
        )
    if not _is_order_paid(order):
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={"order_found": True, "paid": False, "status": order.get("status"), "trade_state": order.get("trade_state")},
            error_code="order_not_paid",
            error_message="order is not paid yet",
        )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
        response_summary={"order_found": True, "paid": True},
        result_summary={"order_projection": "paid_confirmed", "out_trade_no": out_trade_no},
    )


def webhook_order_paid_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    order = _order_from_event(event)
    transaction = _transaction_from_event(event)
    out_trade_no = _text(order.get("out_trade_no") or transaction.get("out_trade_no") or event.aggregate_id)
    target_id = _text(order.get("id") or out_trade_no)
    if not target_id or not out_trade_no:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "aggregate_id": event.aggregate_id},
            response_summary={"external_effect_job_created": False},
            error_code="order_identity_missing",
            error_message="order id or out_trade_no is required",
        )
    external_effects = ExternalEffectService()
    existing_job = external_effects.find_existing_job(
        effect_type=WEBHOOK_ORDER_PAID_PUSH,
        target_type="wechat_pay_order",
        target_id=target_id,
        business_type="commerce_order",
        business_id=out_trade_no,
    )
    if existing_job is not None:
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={
                "external_effect_job_created": False,
                "external_effect_job_reused": True,
                "external_effect_job_id": existing_job.id,
                "effect_type": WEBHOOK_ORDER_PAID_PUSH,
                "execution_mode": existing_job.execution_mode,
                "status": existing_job.status,
            },
            result_summary={
                "external_effect_job_id": existing_job.id,
                "external_effect_job_reused": True,
                "effect_type": WEBHOOK_ORDER_PAID_PUSH,
            },
        )
    job = external_effects.plan_effect(
        effect_type=WEBHOOK_ORDER_PAID_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="wechat_pay_order",
        target_id=target_id,
        business_type="commerce_order",
        business_id=out_trade_no,
        payload={
            "order": {
                "id": order.get("id"),
                "out_trade_no": out_trade_no,
                "status": order.get("status"),
                "trade_state": order.get("trade_state"),
                "product_code": order.get("product_code"),
                "paid_at": str(order.get("paid_at") or ""),
            },
            "transaction": {
                "transaction_id": transaction.get("transaction_id"),
                "trade_state": transaction.get("trade_state"),
                "success_time": transaction.get("success_time"),
            },
            "internal_event_id": event.event_id,
            "domain_event_outbox_id": (event.payload_json or {}).get("domain_event_outbox_id"),
        },
        payload_summary={
            "order_id": order.get("id"),
            "out_trade_no": out_trade_no,
            "status": order.get("status"),
            "trade_state": order.get("trade_state"),
            "internal_event_id": event.event_id,
        },
        context=CommandContext(
            actor_id="internal_event_consumer",
            actor_type="system",
            request_id=event.request_id,
            trace_id=event.trace_id or out_trade_no,
            source_route="/internal-events/payment.succeeded/webhook_order_paid_consumer",
        ),
        source_module="platform_foundation.internal_events.payment",
        source_event_id=event.event_id,
        risk_level="medium",
        requires_approval=False,
        execution_mode="shadow",
        idempotency_key=f"payment.succeeded:{out_trade_no}:external-effect:{WEBHOOK_ORDER_PAID_PUSH}",
    )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
        response_summary={
            "external_effect_job_created": True,
            "external_effect_job_reused": False,
            "external_effect_job_id": job.get("id"),
            "effect_type": WEBHOOK_ORDER_PAID_PUSH,
            "execution_mode": job.get("execution_mode"),
            "status": job.get("status"),
        },
        result_summary={"external_effect_job_id": job.get("id"), "external_effect_job_reused": False, "effect_type": WEBHOOK_ORDER_PAID_PUSH},
    )


def automation_payment_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    order = _order_from_event(event)
    transaction = _transaction_from_event(event)
    if not order:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id},
            response_summary={"automation_processed": False},
            error_code="order_payload_missing",
            error_message="payment.succeeded event is missing the order payload",
        )
    from aicrm_next.automation_runtime_v2.bridge import process_payment_succeeded_event

    result = process_payment_succeeded_event(order=order, transaction=transaction)
    automation_summary = {
        "automation_processed": True,
        "automation_event_id": result.get("event_id"),
        "automation_status": result.get("status") or "processed",
        "automation_reason": result.get("reason") or "",
        "automation_counts": result.get("counts") or {},
    }
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "out_trade_no": _text(order.get("out_trade_no"))},
        response_summary=automation_summary,
        result_summary={"automation_processed": True},
    )


def customer_business_summary_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id},
        response_summary={"skipped": True, "reason": "summary_refresh_not_configured"},
        result_summary={"reason": "summary_refresh_not_configured"},
    )


def dnd_policy_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id},
        response_summary={"skipped": True, "reason": "dnd_policy_not_configured"},
        result_summary={"reason": "dnd_policy_not_configured"},
    )


def ai_assist_notify_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id},
        response_summary={"skipped": True, "reason": "ai_assist_notify_not_configured"},
        result_summary={"reason": "ai_assist_notify_not_configured"},
    )


def register_payment_succeeded_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
    for event_type in PAYMENT_SUCCEEDED_EVENT_TYPES:
        registry.register(event_type, "order_projection_consumer", order_projection_consumer, consumer_type="projection")
        registry.register(event_type, "webhook_order_paid_consumer", webhook_order_paid_consumer, consumer_type="external_effect_planner")
        registry.register(event_type, "automation_payment_consumer", automation_payment_consumer, consumer_type="orchestration")
        registry.register(event_type, "customer_business_summary_consumer", customer_business_summary_consumer, consumer_type="projection")
        registry.register(event_type, "dnd_policy_consumer", dnd_policy_consumer, consumer_type="orchestration")
        registry.register(event_type, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")
