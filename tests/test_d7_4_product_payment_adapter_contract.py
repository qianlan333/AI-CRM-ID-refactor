from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools" / "check_d7_4_product_payment_adapter_contract.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_d7_4_product_payment_adapter_contract", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _d7_4_docs() -> str:
    paths = [
        "docs/d7_4_product_payment_adapter_contract.md",
        "docs/d7_4_product_payment_adapter_implementation_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]
    return "\n".join((REPO_ROOT / path).read_text(encoding="utf-8") for path in paths)


def test_product_write_gateway_contract_exists() -> None:
    from aicrm_next.integration_gateway.payment_adapters import ProductWriteGateway

    for method in ["create_product", "update_product", "enable_product", "disable_product", "delete_product", "build_product_write_preview", "record_product_write_audit"]:
        assert hasattr(ProductWriteGateway, method)


def test_wechat_pay_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.payment_adapters import WeChatPayAdapter

    for method in ["create_jsapi_order", "create_h5_order", "query_order", "close_order", "verify_notify_signature", "parse_notify_payload", "build_checkout_preview"]:
        assert hasattr(WeChatPayAdapter, method)


def test_alipay_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter

    for method in ["create_wap_order", "query_order", "close_order", "verify_notify_signature", "parse_notify_payload", "build_return_preview", "build_checkout_preview"]:
        assert hasattr(AlipayAdapter, method)


def test_payment_notify_gateway_contract_exists() -> None:
    from aicrm_next.integration_gateway.payment_adapters import PaymentNotifyGateway

    for method in ["receive_wechat_notify", "receive_alipay_notify", "build_notify_preview", "record_notify_audit", "build_order_status_update_preview"]:
        assert hasattr(PaymentNotifyGateway, method)


def test_payment_return_gateway_contract_exists() -> None:
    from aicrm_next.integration_gateway.payment_adapters import PaymentReturnGateway

    for method in ["receive_alipay_return", "build_return_page_context", "record_return_audit"]:
        assert hasattr(PaymentReturnGateway, method)


def test_fake_product_create_update_enable_disable_delete_returns_deterministic_fake_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.payment_adapters import ProductWriteGateway

    reset_idempotency_store()
    gateway = ProductWriteGateway("fake")
    first = gateway.create_product(product_code="course_1", page_slug="course-1", amount=9900)
    second = gateway.create_product(product_code="course_1", page_slug="course-1", amount=9900)
    update = gateway.update_product(product_id="prod_001", product_code="course_1", amount=9900)
    enable = gateway.enable_product(product_id="prod_001")
    disable = gateway.disable_product(product_id="prod_001")
    delete = gateway.delete_product(product_id="prod_001")
    assert first["ok"] is True
    assert first["result"] == second["result"]
    assert all(item["result"]["applied"] is False for item in [first, update, enable, disable, delete])
    assert all(item["side_effect_executed"] is False for item in [first, update, enable, disable, delete])


def test_fake_wechat_checkout_returns_deterministic_fake_order_prepay_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.payment_adapters import WeChatPayAdapter

    reset_idempotency_store()
    adapter = WeChatPayAdapter("fake")
    first = adapter.create_jsapi_order(order_id="order_1", product_id="prod_001", openid="openid_1", amount=9900)
    second = adapter.create_jsapi_order(order_id="order_1", product_id="prod_001", openid="openid_1", amount=9900)
    h5 = adapter.create_h5_order(order_id="order_2", product_id="prod_001", amount=9900)
    assert first["result"] == second["result"]
    assert first["result"]["prepay_id"].startswith("fake_prepay_")
    assert h5["result"]["provider_called"] is False


def test_fake_alipay_checkout_returns_deterministic_fake_payment_url_result() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter

    reset_idempotency_store()
    adapter = AlipayAdapter("fake")
    first = adapter.create_wap_order(order_id="order_1", product_id="prod_001", payer_id="payer_1", amount=9900)
    second = adapter.create_wap_order(order_id="order_1", product_id="prod_001", payer_id="payer_1", amount=9900)
    assert first["result"] == second["result"]
    assert first["result"]["payment_url"].startswith("https://fake-pay.local/alipay/checkout/")
    assert first["result"]["provider_called"] is False


def test_fake_notify_and_return_paths_are_deterministic() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter, PaymentNotifyGateway, PaymentReturnGateway, WeChatPayAdapter

    reset_idempotency_store()
    wechat_adapter = WeChatPayAdapter("fake")
    alipay_adapter = AlipayAdapter("fake")
    notify_gateway = PaymentNotifyGateway("fake")
    return_gateway = PaymentReturnGateway("fake")
    wechat_parse_a = wechat_adapter.parse_notify_payload(notify_id="notify_1", provider_payload={"private_key": "secret", "status": "paid"})
    wechat_parse_b = wechat_adapter.parse_notify_payload(notify_id="notify_1", provider_payload={"private_key": "secret", "status": "paid"})
    alipay_parse = alipay_adapter.parse_notify_payload(notify_id="notify_2", provider_payload={"app_secret": "secret", "status": "paid"})
    wechat_notify_a = notify_gateway.receive_wechat_notify(order_id="order_1", transaction_id="tx_1", notify_id="notify_1", amount=9900)
    wechat_notify_b = notify_gateway.receive_wechat_notify(order_id="order_1", transaction_id="tx_1", notify_id="notify_1", amount=9900)
    alipay_notify = notify_gateway.receive_alipay_notify(order_id="order_2", transaction_id="tx_2", notify_id="notify_2", amount=9900)
    alipay_return = return_gateway.receive_alipay_return(order_id="order_2", transaction_id="tx_2", status="paid")
    assert wechat_parse_a["result"] == wechat_parse_b["result"]
    assert "private_key" not in wechat_parse_a["target"]
    assert "app_secret" not in alipay_parse["target"]
    assert wechat_notify_a["result"] == wechat_notify_b["result"]
    assert wechat_notify_a["result"]["would_update_order"] is False
    assert alipay_notify["result"]["would_update_order"] is False
    assert alipay_return["result"]["return_processed"] is False


def test_repeated_call_with_same_idempotency_key_returns_same_result() -> None:
    from aicrm_next.integration_gateway.payment_adapters import WeChatPayAdapter

    adapter = WeChatPayAdapter("fake")
    first = adapter.create_h5_order(order_id="order_1", amount=9900, idempotency_key="idem-pay-1")
    second = adapter.create_h5_order(order_id="order_2", amount=19900, idempotency_key="idem-pay-1")
    assert first["result"] == second["result"]


def test_disabled_mode_returns_stable_disabled_error() -> None:
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter

    result = AlipayAdapter("disabled").create_wap_order(order_id="order_1", amount=9900)
    assert result["ok"] is False
    assert result["error_code"] == "adapter_disabled"
    assert result["side_effect_executed"] is False


def test_production_mode_without_explicit_env_flag_fails_closed(monkeypatch) -> None:
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter, PaymentNotifyGateway, ProductWriteGateway, WeChatPayAdapter

    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_WECHAT_PAY", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_ALIPAY", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY", raising=False)
    results = [
        ProductWriteGateway("production").create_product(product_code="course_1"),
        WeChatPayAdapter("production").create_h5_order(order_id="order_1", amount=9900),
        AlipayAdapter("production").create_wap_order(order_id="order_2", amount=9900),
        PaymentNotifyGateway("production").receive_wechat_notify(order_id="order_1"),
    ]
    assert all(result["ok"] is False for result in results)
    assert all(result["error_code"] == "production_guard_failed" for result in results)


def test_production_mode_with_env_flag_still_returns_not_implemented(monkeypatch) -> None:
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter, PaymentNotifyGateway, ProductWriteGateway, WeChatPayAdapter

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES", "true")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_WECHAT_PAY", "true")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_ALIPAY", "true")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY", "true")
    results = [
        ProductWriteGateway("production").create_product(product_code="course_1"),
        WeChatPayAdapter("production").create_h5_order(order_id="order_1", amount=9900),
        AlipayAdapter("production").create_wap_order(order_id="order_2", amount=9900),
        PaymentNotifyGateway("production").receive_wechat_notify(order_id="order_1"),
    ]
    assert all(result["ok"] is False for result in results)
    assert all(result["error_code"] == "production_not_implemented" for result in results)


def test_side_effect_executed_is_false_in_fake_disabled_staging_guarded_production(monkeypatch) -> None:
    from aicrm_next.integration_gateway.payment_adapters import WeChatPayAdapter

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_WECHAT_PAY", "true")
    results = [
        WeChatPayAdapter("fake").create_h5_order(order_id="order_1", amount=9900),
        WeChatPayAdapter("disabled").create_h5_order(order_id="order_1", amount=9900),
        WeChatPayAdapter("staging").create_h5_order(order_id="order_1", amount=9900),
        WeChatPayAdapter("production").create_h5_order(order_id="order_1", amount=9900),
    ]
    assert all(result["side_effect_executed"] is False for result in results)
    assert results[-1]["error_code"] == "production_not_implemented"


def test_audit_record_is_created_for_product_write_checkout_notify_and_return() -> None:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.payment_adapters import AlipayAdapter, PaymentNotifyGateway, PaymentReturnGateway, ProductWriteGateway, WeChatPayAdapter

    reset_audit_events()
    ProductWriteGateway("fake").create_product(product_code="course_1")
    WeChatPayAdapter("fake").create_h5_order(order_id="order_1", amount=9900)
    AlipayAdapter("fake").create_wap_order(order_id="order_2", amount=9900)
    PaymentNotifyGateway("fake").receive_wechat_notify(order_id="order_1")
    PaymentReturnGateway("fake").receive_alipay_return(order_id="order_2", status="paid")
    events = list_audit_events()
    assert [event["adapter"] for event in events[-5:]] == ["ProductWriteGateway", "WeChatPayAdapter", "AlipayAdapter", "PaymentNotifyGateway", "PaymentReturnGateway"]
    assert all(event["side_effect_executed"] is False for event in events[-5:])


class _SpyProductGateway:
    mode = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_product(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_product")
        return {"ok": True, "adapter": "SpyProduct", "mode": "fake", "operation": "create_product", "idempotency_key": "spy-product", "target": kwargs, "result": {"applied": False}, "audit_id": "spy-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}


class _SpyWechatAdapter:
    mode = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_jsapi_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_jsapi_order")
        return {"ok": True, "adapter": "SpyWechat", "mode": "fake", "operation": "create_jsapi_order", "idempotency_key": "spy-wechat", "target": kwargs, "result": {"checkout_url": "https://fake-pay.local/wechat/checkout/order", "qr_code_url": "https://fake-pay.local/wechat/qr/order.png", "source_status": "fake"}, "audit_id": "spy-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def create_h5_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_h5_order")
        return self.create_jsapi_order(**kwargs)


class _SpyAlipayAdapter:
    mode = "fake"

    def __init__(self) -> None:
        self.called = False

    def create_wap_order(self, **kwargs: Any) -> dict[str, Any]:
        self.called = True
        return {"ok": True, "adapter": "SpyAlipay", "mode": "fake", "operation": "create_wap_order", "idempotency_key": "spy-alipay", "target": kwargs, "result": {"checkout_url": "https://fake-pay.local/alipay/checkout/order", "qr_code_url": "https://fake-pay.local/alipay/qr/order.png", "source_status": "fake"}, "audit_id": "spy-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}


class _SpyNotifyGateway:
    mode = "fake"

    def __init__(self) -> None:
        self.called = False

    def receive_wechat_notify(self, **kwargs: Any) -> dict[str, Any]:
        self.called = True
        return {"ok": True, "adapter": "SpyNotify", "mode": "fake", "operation": "receive_wechat_notify", "idempotency_key": "spy-notify", "target": kwargs, "result": {"would_update_order": False}, "audit_id": "spy-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}

    def receive_alipay_notify(self, **kwargs: Any) -> dict[str, Any]:
        return self.receive_wechat_notify(**kwargs)

    def build_order_status_update_preview(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "adapter": "SpyNotify", "mode": "fake", "operation": "build_order_status_update_preview", "idempotency_key": "spy-status", "target": kwargs, "result": {"would_update_order": False}, "audit_id": "spy-audit", "side_effect_executed": False, "error_code": "", "error_message": ""}


def test_product_write_api_uses_product_write_gateway_boundary() -> None:
    from aicrm_next.commerce.application import UpsertProductCommand
    from aicrm_next.commerce.dto import ProductUpsertRequest
    from aicrm_next.commerce.repo import InMemoryCommerceRepository

    gateway = _SpyProductGateway()
    result = UpsertProductCommand(repo=InMemoryCommerceRepository(), product_write_gateway=gateway)(ProductUpsertRequest(product_code="course_new", title="Course", price_cents=9900))
    assert result["ok"] is True
    assert gateway.calls == ["create_product"]
    assert result["adapter_contract"]["product_write"]["adapter"] == "SpyProduct"


def test_wechat_checkout_fake_path_uses_wechat_adapter_boundary() -> None:
    from aicrm_next.commerce.application import CheckoutCommand
    from aicrm_next.commerce.dto import CheckoutRequest
    from aicrm_next.commerce.repo import InMemoryCommerceRepository

    adapter = _SpyWechatAdapter()
    result = CheckoutCommand("wechat", repo=InMemoryCommerceRepository(), wechat_adapter=adapter)(CheckoutRequest(product_code="course_masked_001"))
    assert result["ok"] is True
    assert adapter.calls[0] == "create_h5_order"
    assert result["adapter_contract"]["checkout"]["adapter"] == "SpyWechat"


def test_alipay_checkout_fake_path_uses_alipay_adapter_boundary() -> None:
    from aicrm_next.commerce.application import CheckoutCommand
    from aicrm_next.commerce.dto import CheckoutRequest
    from aicrm_next.commerce.repo import InMemoryCommerceRepository

    adapter = _SpyAlipayAdapter()
    result = CheckoutCommand("alipay", repo=InMemoryCommerceRepository(), alipay_adapter=adapter)(CheckoutRequest(product_code="course_masked_001"))
    assert result["ok"] is True
    assert adapter.called is True
    assert result["adapter_contract"]["checkout"]["adapter"] == "SpyAlipay"


def test_notify_fake_path_uses_payment_notify_gateway_boundary() -> None:
    from aicrm_next.commerce.application import NotifyPaymentCommand
    from aicrm_next.commerce.dto import PaymentNotifyRequest
    from aicrm_next.commerce.repo import InMemoryCommerceRepository

    gateway = _SpyNotifyGateway()
    result = NotifyPaymentCommand("wechat", repo=InMemoryCommerceRepository(), notify_gateway=gateway)(PaymentNotifyRequest(order_no="order_masked_001", transaction_id="tx_1"))
    assert result["ok"] is True
    assert gateway.called is True
    assert result["adapter_contract"]["notify"]["adapter"] == "SpyNotify"


def test_alipay_return_api_uses_payment_return_gateway_boundary() -> None:
    from fastapi.testclient import TestClient

    from aicrm_next.main import create_app

    response = TestClient(create_app()).get("/api/alipay/return", params={"order_no": "order_masked_001", "status": "paid"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_contract"]["return"]["adapter"] == "PaymentReturnGateway"
    assert payload["adapter_contract"]["return"]["side_effect_executed"] is False


def test_product_smoke_remains_pass() -> None:
    from tools import product_management_gray_smoke as smoke

    report = smoke.run_smoke(Namespace(next_testclient=True, next_base_url="", include_fake_writes=True, output_md="/tmp/unused.md", output_json="/tmp/unused.json"))
    assert report["ok"] is True
    assert report["side_effect_safety"]["payment_provider_called"] is False


def test_commerce_parity_remains_pass() -> None:
    from tools import compare_commerce_parity as parity

    report = parity.run_compare(
        Namespace(
            old_base_url="",
            next_base_url="",
            old_fixture_dir=str(REPO_ROOT / "experiments/ai_crm_next/tests/fixtures/old_commerce"),
            next_testclient=True,
            allow_old_write_endpoints=False,
            output_md="/tmp/unused.md",
            output_json="/tmp/unused.json",
        )
    )
    assert report["ok"] is True
    assert report["side_effect_safety"]["old_write_endpoints_enabled"] is False


def test_docs_do_not_mark_production_ready_or_delete_ready() -> None:
    docs = _d7_4_docs()
    assert "production_ready" not in docs
    assert "delete_ready" not in docs


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in text
        assert "legacy_flask_app" not in text


def test_d7_4_checker_reports_pass(tmp_path: Path) -> None:
    checker = _load_checker()
    report = checker.build_report()
    assert report["ok"] is True
    assert report["side_effect_safety"]["real_wechat_pay_executed"] is False
    assert report["side_effect_safety"]["real_alipay_executed"] is False
