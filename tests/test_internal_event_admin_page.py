from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.internal_events import (
    InternalEventConsumerRegistry,
    InternalEventConsumerResult,
    InternalEventService,
    reset_internal_event_fixture_state,
)
from aicrm_next.platform_foundation.internal_events.repository import build_internal_event_repository


def _seed_page_event() -> None:
    reset_internal_event_fixture_state()
    registry = InternalEventConsumerRegistry()
    for name in [
        "order_projection_consumer",
        "webhook_order_paid_consumer",
        "automation_payment_consumer",
        "customer_business_summary_consumer",
        "dnd_policy_consumer",
        "ai_assist_notify_consumer",
    ]:
        registry.register("payment.succeeded", name, lambda event, run: InternalEventConsumerResult(status="succeeded"))
    InternalEventService(build_internal_event_repository(), registry).emit_event(
        event_type="payment.succeeded",
        aggregate_type="wechat_pay_order",
        aggregate_id="77",
        subject_type="customer",
        subject_id="wm_page_event",
        idempotency_key="payment.succeeded:WXP_PAGE_EVENT",
        source_module="public_product.h5_wechat_pay",
        context=CommandContext(trace_id="WXP_PAGE_EVENT", source_route="/api/h5/wechat-pay/notify"),
        payload_summary={"out_trade_no": "WXP_PAGE_EVENT", "phone": "13800001234", "safe": "visible"},
    )


def test_internal_event_admin_page_smoke_and_payment_consumer_copy(next_client: TestClient) -> None:
    _seed_page_event()

    response = next_client.get("/admin/internal-events")

    assert response.status_code == 200
    assert "事件中心" in response.text
    assert 'data-route-owner="ai_crm_next"' in response.text
    assert 'id="statsGrid"' in response.text
    assert 'id="filterForm"' in response.text
    assert 'id="internalEventsTable"' in response.text
    assert 'id="detailPanel"' in response.text
    for text in [
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "subject_type",
        "subject_id",
        "consumer_name",
        "consumer_status",
        "trace_id",
        "source_module",
        "created_from",
        "created_to",
        "payment.succeeded",
        "订单消费者",
        "webhook 消费者",
        "自动化消费者",
        "客户摘要消费者",
        "DND 消费者",
        "AI 助手消费者",
        "成功",
        "失败可重试",
        "已跳过",
        "payload_summary_json",
        "/api/admin/internal-events",
        'data-action="retry"',
        'data-action="skip"',
        'href="#refresh"',
        'href="#export"',
    ]:
        assert text in response.text
    assert "payload_json" not in response.text
    assert "13800001234" not in response.text
    assert "openid" not in response.text.lower()
    assert "unionid" not in response.text.lower()
    assert "secret" not in response.text.lower()
    assert "access_token" not in response.text


def test_internal_event_navigation_entry_is_in_admin_shell(next_client: TestClient) -> None:
    response = next_client.get("/admin/internal-events")

    assert response.status_code == 200
    assert 'href="/admin/internal-events"' in response.text
    assert "事件中心" in response.text
