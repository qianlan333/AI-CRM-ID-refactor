from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payment_final_docs_describe_known_deprecated_and_replacement_paths() -> None:
    text = (ROOT / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md").read_text(encoding="utf-8")

    for phrase in [
        "products/lead-plans",
        "replacement `products/lead-channels`",
        "order-exports/{job_id}",
        "replacement `order-exports`",
        "legacy Alipay admin APIs",
        "public replacements are `/api/checkout/wechat`, `/api/orders/{order_no}`, `/api/wechat-pay/notify`",
        "public replacements are `/api/checkout/alipay`, `/api/orders/{order_no}`, `/api/alipay/notify`, `/api/alipay/return`",
        "No route in this inventory falls back to `production_compat`",
    ]:
        assert phrase in text


def test_payment_final_contract_notes_block_real_money_movement() -> None:
    text = (ROOT / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md").read_text(encoding="utf-8")

    for phrase in [
        "no route calls a real provider",
        "no route performs real signature verification",
        "no route executes a real refund",
        "payment_request_executed=false",
        "provider_signature_verified=false",
        "real_refund_executed=false",
        "Unknown child path responses are controlled by Next",
    ]:
        assert phrase in text
