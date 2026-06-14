from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from aicrm_next.platform_foundation.external_effects import WEBHOOK_ORDER_PAID_PUSH, ExternalEffectService, reset_external_effect_fixture_state
from aicrm_next.platform_foundation.internal_events import InternalEventService, reset_internal_event_fixture_state
from aicrm_next.platform_foundation.internal_events.payment import PAYMENT_SUCCEEDED_EVENT_TYPE
from aicrm_next.platform_foundation.internal_events.worker import InternalEventWorker
from aicrm_next.public_product import h5_wechat_pay
from aicrm_next.public_product.h5_wechat_pay import _apply_transaction


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _PaymentConn:
    def __init__(self):
        self.order = {
            "id": 77,
            "out_trade_no": "WXP_INTERNAL_PAYMENT",
            "product_code": "subscription_trial_month",
            "product_name": "Internal Payment Slice",
            "amount_total": 990,
            "payer_total": 990,
            "status": "paying",
            "trade_state": "NOTPAY",
            "external_userid": "wm_internal_payment",
            "userid_snapshot": "user_internal",
            "respondent_key": "respondent_internal",
            "mobile_snapshot": "13800001234",
            "paid_at": "",
        }
        self.queries: list[str] = []

    def execute(self, query, params):
        self.queries.append(query)
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT * FROM wechat_pay_orders"):
            return _FakeCursor(dict(self.order))
        if normalized.startswith("UPDATE wechat_pay_orders"):
            self.order.update(
                {
                    "status": params[0],
                    "trade_state": params[1],
                    "transaction_id": params[2],
                    "bank_type": params[3],
                    "payer_openid": params[4] or self.order.get("payer_openid", ""),
                    "payer_total": params[5],
                    "paid_at": params[7],
                    "notify_payload_json": params[8],
                }
            )
            return _FakeCursor(dict(self.order))
        raise AssertionError(query)


def _transaction(out_trade_no: str = "WXP_INTERNAL_PAYMENT") -> dict:
    return {
        "out_trade_no": out_trade_no,
        "trade_state": "SUCCESS",
        "transaction_id": f"wx_tx_{out_trade_no}",
        "bank_type": "OTHERS",
        "success_time": "2026-06-13T10:00:00+08:00",
        "amount": {"payer_total": 990},
        "payer": {"openid": "openid_internal"},
    }


def _enable_payment_events(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_PAYMENT_DISABLE_LEGACY_AUTOMATION_DIRECT", "1")


def _reset_state() -> None:
    reset_internal_event_fixture_state()
    reset_external_effect_fixture_state()


def _patch_legacy_outbox(monkeypatch, outbox_id: int = 9001) -> list[dict]:
    calls: list[dict] = []

    def fake_enqueue(conn, order):
        calls.append(dict(order))
        return {"id": outbox_id, "event_type": "transaction.paid"}

    monkeypatch.setattr(h5_wechat_pay, "enqueue_transaction_paid_outbox", fake_enqueue)
    return calls


def test_payment_success_emits_payment_succeeded_and_duplicate_notify_is_idempotent(monkeypatch) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)
    direct_runtime_calls: list[dict] = []
    monkeypatch.setattr(
        "aicrm_next.automation_runtime_v2.bridge.process_payment_succeeded_event",
        lambda *, order, transaction: direct_runtime_calls.append({"order": order, "transaction": transaction}),
    )

    conn = _PaymentConn()
    first = _apply_transaction(conn, _transaction())
    second = _apply_transaction(conn, _transaction())
    events, event_total = InternalEventService().list_events({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})
    runs, run_total = InternalEventService().list_consumer_runs({"event_id": events[0].event_id})

    assert first["status"] == "paid"
    assert second["status"] == "paid"
    assert event_total == 1
    assert events[0].event_type == "payment.succeeded"
    assert events[0].aggregate_type == "wechat_pay_order"
    assert events[0].aggregate_id == "77"
    assert events[0].subject_type == "customer"
    assert events[0].subject_id == "wm_internal_payment"
    assert events[0].idempotency_key == "payment.succeeded:WXP_INTERNAL_PAYMENT"
    assert events[0].source_module == "public_product.h5_wechat_pay"
    assert events[0].source_route == "/api/h5/wechat-pay/notify"
    assert events[0].trace_id == "WXP_INTERNAL_PAYMENT"
    assert events[0].payload_summary_json["mobile_masked"] == "138****1234"
    assert "13800001234" not in str(events[0].payload_summary_json)
    assert run_total == 6
    assert sorted(run.consumer_name for run in runs) == [
        "ai_assist_notify_consumer",
        "automation_payment_consumer",
        "customer_business_summary_consumer",
        "dnd_policy_consumer",
        "order_projection_consumer",
        "webhook_order_paid_consumer",
    ]
    assert direct_runtime_calls == []


def test_webhook_order_paid_consumer_creates_external_effect_job_without_external_call(monkeypatch) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)
    conn = _PaymentConn()
    _apply_transaction(conn, _transaction())
    event = InternalEventService().list_events({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})[0][0]
    legacy_jobs, legacy_total = ExternalEffectService().list_jobs({"effect_type": WEBHOOK_ORDER_PAID_PUSH, "business_id": "WXP_INTERNAL_PAYMENT"})
    legacy_job = legacy_jobs[0]

    result = InternalEventWorker().run_due(batch_size=1, dry_run=False, consumer_names=["webhook_order_paid_consumer"])
    jobs, total = ExternalEffectService().list_jobs({"effect_type": WEBHOOK_ORDER_PAID_PUSH, "business_id": "WXP_INTERNAL_PAYMENT"})
    attempts = ExternalEffectService().list_attempts(legacy_job.id)
    response_summary = result["items"][0]["attempt"]["response_summary_json"]

    assert legacy_total == 1
    assert result["counts"]["succeeded_count"] == 1
    assert result["real_external_call_executed"] is False
    assert total == 1
    assert jobs[0].id == legacy_job.id
    assert jobs[0].idempotency_key == f"wechat-pay:WXP_INTERNAL_PAYMENT:external-effect:{WEBHOOK_ORDER_PAID_PUSH}"
    assert jobs[0].execution_mode == "shadow"
    assert jobs[0].status == "planned"
    assert attempts == []
    assert response_summary["external_effect_job_reused"] is True
    assert response_summary["external_effect_job_created"] is False
    assert response_summary["external_effect_job_id"] == legacy_job.id
    assert event.event_id


def test_automation_payment_consumer_executes_and_records_attempt(monkeypatch) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)
    automation_calls: list[dict] = []

    def fake_automation(*, order, transaction):
        automation_calls.append({"order": dict(order), "transaction": dict(transaction)})
        return {"ok": True, "processed": [{"event": "payment_succeeded"}]}

    monkeypatch.setattr("aicrm_next.automation_runtime_v2.bridge.process_payment_succeeded_event", fake_automation)
    _apply_transaction(_PaymentConn(), _transaction())
    event = InternalEventService().list_events({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})[0][0]

    result = InternalEventWorker().run_due(batch_size=1, dry_run=False, consumer_names=["automation_payment_consumer"])
    runs, _ = InternalEventService().list_consumer_runs({"event_id": event.event_id, "consumer_name": "automation_payment_consumer"})
    attempts = InternalEventService().list_attempts(event_id=event.event_id)

    assert result["counts"]["succeeded_count"] == 1
    assert len(automation_calls) == 1
    assert automation_calls[0]["order"]["out_trade_no"] == "WXP_INTERNAL_PAYMENT"
    assert runs[0].status == "succeeded"
    assert [attempt for attempt in attempts if attempt.consumer_name == "automation_payment_consumer"][0].status == "succeeded"


def test_automation_payment_consumer_handles_datetime_payload_without_terminal_failure(monkeypatch, next_pg_schema) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)
    conn = _PaymentConn()
    transaction = _transaction()
    transaction["success_time"] = datetime(2026, 6, 14, 12, 42, 36, tzinfo=timezone.utc)
    transaction["amount"]["payer_total"] = Decimal("990")
    transaction["nested"] = {"seen_at": [datetime(2026, 6, 14, 12, 43, 0, tzinfo=timezone.utc)]}
    _apply_transaction(conn, transaction)
    event = InternalEventService().list_events({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})[0][0]

    result = InternalEventWorker().run_due(batch_size=1, dry_run=False, consumer_names=["automation_payment_consumer"])
    runs, _ = InternalEventService().list_consumer_runs({"event_id": event.event_id, "consumer_name": "automation_payment_consumer"})
    attempts = [attempt for attempt in InternalEventService().list_attempts(event_id=event.event_id) if attempt.consumer_name == "automation_payment_consumer"]

    assert result["counts"]["succeeded_count"] == 1
    assert result["counts"]["failed_terminal_count"] == 0
    assert runs[0].status == "succeeded"
    assert runs[0].result_summary_json["automation_processed"] is True
    assert attempts[0].status == "succeeded"
    assert attempts[0].response_summary_json["automation_processed"] is True


def test_webhook_order_paid_consumer_creates_shadow_job_when_no_existing_legacy_job(monkeypatch) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)
    _apply_transaction(_PaymentConn(), _transaction())
    reset_external_effect_fixture_state()
    event = InternalEventService().list_events({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})[0][0]

    result = InternalEventWorker().run_due(batch_size=1, dry_run=False, consumer_names=["webhook_order_paid_consumer"])
    jobs, total = ExternalEffectService().list_jobs({"effect_type": WEBHOOK_ORDER_PAID_PUSH, "business_id": "WXP_INTERNAL_PAYMENT"})
    attempts = ExternalEffectService().list_attempts(jobs[0].id)
    response_summary = result["items"][0]["attempt"]["response_summary_json"]

    assert result["counts"]["succeeded_count"] == 1
    assert total == 1
    assert jobs[0].idempotency_key == f"payment.succeeded:WXP_INTERNAL_PAYMENT:external-effect:{WEBHOOK_ORDER_PAID_PUSH}"
    assert jobs[0].execution_mode == "shadow"
    assert jobs[0].status == "planned"
    assert attempts == []
    assert response_summary["external_effect_job_reused"] is False
    assert response_summary["external_effect_job_created"] is True


def test_dnd_consumer_is_skipped_with_visible_reason(monkeypatch) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)
    _apply_transaction(_PaymentConn(), _transaction())
    event = InternalEventService().list_events({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})[0][0]

    result = InternalEventWorker().run_due(batch_size=1, dry_run=False, consumer_names=["dnd_policy_consumer"])
    runs, _ = InternalEventService().list_consumer_runs({"event_id": event.event_id, "consumer_name": "dnd_policy_consumer"})
    attempts = [attempt for attempt in InternalEventService().list_attempts(event_id=event.event_id) if attempt.consumer_name == "dnd_policy_consumer"]

    assert result["counts"]["skipped_count"] == 1
    assert runs[0].status == "skipped"
    assert runs[0].result_summary_json["reason"] == "dnd_policy_not_configured"
    assert attempts[0].status == "skipped"
    assert attempts[0].response_summary_json["reason"] == "dnd_policy_not_configured"


def test_consumer_failure_does_not_affect_payment_apply_result(monkeypatch) -> None:
    _reset_state()
    _enable_payment_events(monkeypatch)
    _patch_legacy_outbox(monkeypatch)

    def broken_automation(*, order, transaction):
        raise RuntimeError("automation temporarily down")

    monkeypatch.setattr("aicrm_next.automation_runtime_v2.bridge.process_payment_succeeded_event", broken_automation)
    order = _apply_transaction(_PaymentConn(), _transaction())
    result = InternalEventWorker().run_due(batch_size=1, dry_run=False, consumer_names=["automation_payment_consumer"])

    assert order["status"] == "paid"
    assert result["counts"]["failed_retryable_count"] == 1
    assert result["items"][0]["attempt"]["error_code"] == "handler_exception"
