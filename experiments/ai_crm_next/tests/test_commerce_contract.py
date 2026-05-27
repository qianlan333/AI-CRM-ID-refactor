from __future__ import annotations

from conftest import make_client


def test_product_list_and_detail_return_required_shape() -> None:
    client = make_client()
    payload = client.get("/api/admin/wechat-pay/products").json()
    assert payload["ok"] is True
    assert {"items", "total", "limit", "offset"} <= set(payload)
    item = payload["items"][0]
    for key in [
        "id",
        "product_code",
        "title",
        "description",
        "price_cents",
        "currency",
        "enabled",
        "page_slug",
        "cover_image_id",
        "detail_image_ids",
        "buy_button_text",
        "created_at",
        "updated_at",
    ]:
        assert key in item
    detail = client.get(f"/api/admin/wechat-pay/products/{item['id']}").json()
    assert detail["ok"] is True
    assert "detail_sections" in detail["product"]


def test_product_create_update_enable_disable_delete_and_validation() -> None:
    client = make_client()
    payload = {
        "product_code": "course_masked_new",
        "title": "新商品",
        "description": "fixture",
        "price_cents": 100,
        "page_slug": "course-masked-new",
    }
    created = client.post("/api/admin/wechat-pay/products", json=payload)
    assert created.status_code == 200
    product = created.json()["product"]
    assert client.post("/api/admin/wechat-pay/products", json=payload).status_code == 400
    assert client.post("/api/admin/wechat-pay/products", json={**payload, "product_code": "bad_price", "price_cents": -1}).status_code == 400
    updated = client.put(f"/api/admin/wechat-pay/products/{product['id']}", json={**payload, "title": "更新商品"}).json()
    assert updated["product"]["title"] == "更新商品"
    assert client.post(f"/api/admin/wechat-pay/products/{product['id']}/disable").json()["product"]["enabled"] is False
    assert client.post(f"/api/admin/wechat-pay/products/{product['id']}/enable").json()["product"]["enabled"] is True
    deleted = client.delete(f"/api/admin/wechat-pay/products/{product['id']}").json()
    assert deleted["soft_deleted"] is True


def test_checkout_orders_notify_and_transactions_are_fake_and_idempotent() -> None:
    client = make_client()
    seeded_detail = client.get("/admin/wechat-pay/transactions/order_masked_001")
    assert seeded_detail.status_code == 200
    assert "申请退款" in seeded_detail.text
    assert "可退款" in seeded_detail.text
    mismatch = client.post(
        "/api/admin/wechat-pay/orders/order_masked_001/refunds",
        json={
            "refund_amount_total": 100,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "wrong_transaction",
            "checked": True,
        },
    )
    assert mismatch.status_code == 400
    assert "微信单号二次确认不匹配" in mismatch.json()["error"]
    refund = client.post(
        "/api/admin/wechat-pay/orders/order_masked_001/refunds",
        json={
            "refund_amount_total": 100,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "transaction_masked_001",
            "checked": True,
        },
    ).json()
    assert refund["ok"] is True
    assert refund["refund"]["provider_refund_executed"] is False
    assert refund["order"]["status"] == "refund_processing"
    assert refund["order"]["active_refund_amount_total"] == 100

    wechat = client.post(
        "/api/checkout/wechat",
        json={"product_code": "course_masked_001", "buyer_identity": {"mobile": "mobile_masked_001"}, "quantity": 2},
    ).json()
    assert wechat["ok"] is True
    assert wechat["payment_provider"] == "wechat"
    assert wechat["payment_status"] == "pending"
    assert wechat["fake_payment"] is True
    assert client.post("/api/checkout/wechat", json={"product_code": "course_masked_001", "quantity": 0}).status_code == 400
    assert client.post("/api/checkout/wechat", json={"product_code": "missing", "quantity": 1}).status_code == 404
    assert client.post("/api/checkout/wechat", json={"product_code": "course_disabled_001", "quantity": 1}).status_code == 400

    status = client.get(f"/api/orders/{wechat['order_no']}/status").json()
    assert status["payment_status"] == "pending"
    paid = client.post(
        "/api/wechat-pay/notify",
        json={"order_no": wechat["order_no"], "payment_status": "paid", "transaction_id": "transaction_masked_new"},
    ).json()
    paid_again = client.post(
        "/api/wechat-pay/notify",
        json={"order_no": wechat["order_no"], "payment_status": "paid", "transaction_id": "transaction_masked_new"},
    ).json()
    assert paid["payment_status"] == "paid"
    assert paid_again["transaction_id"] == "transaction_masked_new"
    assert client.post("/api/wechat-pay/notify", json={"order_no": wechat["order_no"], "payment_status": "failed"}).json()["payment_status"] == "failed"

    alipay = client.post(
        "/api/checkout/alipay",
        json={"product_code": "course_masked_001", "buyer_identity": {"openid": "openid_masked_001"}, "quantity": 1},
    ).json()
    assert alipay["payment_provider"] == "alipay"
    assert client.get(f"/api/alipay/return?order_no={alipay['order_no']}&status=paid").json()["payment_status"] == "paid"

    wx_tx = client.get("/api/admin/wechat-pay/transactions?payment_status=failed&product_code=course_masked_001&mobile=mobile_masked").json()
    assert wx_tx["ok"] is True
    assert wx_tx["items"][0]["order_no"] == wechat["order_no"]
    wx_admin_orders = client.get("/api/admin/wechat-pay/orders?status=failed&product_code=course_masked_001&mobile=mobile_masked").json()
    assert wx_admin_orders["ok"] is True
    assert wx_admin_orders["items"][0]["transaction_id"] == "transaction_masked_new"
    assert wx_admin_orders["items"][0]["status_label"] == "支付失败"
    assert client.get(f"/api/admin/wechat-pay/transactions/{wechat['order_no']}").json()["transaction"]["payment_status"] == "failed"
    detail_page = client.get(f"/admin/wechat-pay/transactions/{wechat['order_no']}")
    assert detail_page.status_code == 200
    assert "微信支付订单详情" in detail_page.text
    assert "transaction_masked_new" in detail_page.text
    assert client.get("/api/admin/alipay/transactions?payment_status=paid").json()["ok"] is True

    export_response = client.post("/api/admin/wechat-pay/order-exports", json={"filters": {"product_code": "course_masked_001"}})
    assert export_response.status_code == 200
    assert "text/csv" in export_response.headers["content-type"]
    assert "微信单号" in export_response.text


def test_public_product_page_and_unknown_product_contracts() -> None:
    client = make_client()
    assert client.get("/p/course-masked-001").status_code == 200
    product = client.get("/api/products/course-masked-001").json()["product"]
    assert product["product_code"] == "course_masked_001"
    assert client.get("/api/products/missing-product").status_code == 404
