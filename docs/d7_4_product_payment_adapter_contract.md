# D7.4 Product Payment Adapter Contract

## Scope

D7.4 moves Product writes, WeChat Pay checkout, Alipay checkout, payment notify, and Alipay return into the `aicrm_next.integration_gateway` adapter boundary. This slice is contract-only and fake/staging-disabled by default.

It does not call WeChat Pay, does not call Alipay, does not generate production payment orders, does not verify production notify signatures, does not process production notify callbacks, does not write production payment state, does not read provider credentials, and does not change production config or traffic.

## Contracts

`ProductWriteGateway` owns:

- `create_product`
- `update_product`
- `enable_product`
- `disable_product`
- `delete_product`
- `build_product_write_preview`
- `record_product_write_audit`

`WeChatPayAdapter` owns:

- `create_jsapi_order`
- `create_h5_order`
- `query_order`
- `close_order`
- `verify_notify_signature`
- `parse_notify_payload`
- `build_checkout_preview`

`AlipayAdapter` owns:

- `create_wap_order`
- `query_order`
- `close_order`
- `verify_notify_signature`
- `parse_notify_payload`
- `build_return_preview`
- `build_checkout_preview`

`PaymentNotifyGateway` owns:

- `receive_wechat_notify`
- `receive_alipay_notify`
- `build_notify_preview`
- `record_notify_audit`
- `build_order_status_update_preview`

`PaymentReturnGateway` owns:

- `receive_alipay_return`
- `build_return_page_context`
- `record_return_audit`

Every method returns the stable adapter shape:

- `ok`
- `adapter`
- `mode`
- `operation`
- `idempotency_key`
- `target`
- `result`
- `audit_id`
- `side_effect_executed`
- `error_code`
- `error_message`

Targets may include product, page, order, transaction, provider, payer, amount, currency, and notify identifiers. Secret, private key, API key, token, certificate, merchant key, and credential-shaped fields are scrubbed from target payloads.

## Modes

Default modes:

- `AICRM_NEXT_PRODUCT_WRITE_MODE=fake`
- `AICRM_NEXT_WECHAT_PAY_MODE=fake`
- `AICRM_NEXT_ALIPAY_MODE=fake`
- `AICRM_NEXT_PAYMENT_NOTIFY_MODE=fake`

Production guard flags:

- `AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES=true`
- `AICRM_NEXT_ENABLE_REAL_WECHAT_PAY=true`
- `AICRM_NEXT_ENABLE_REAL_ALIPAY=true`
- `AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY=true`

Behavior:

- `fake`: returns deterministic fake results and audit records; no external calls.
- `disabled`: returns `adapter_disabled` and audit records.
- `staging`: returns staging-shaped fake results and audit records; no external calls.
- `production`: fails closed without the explicit env flag. Even with the flag enabled in D7.4, it returns `production_not_implemented`.

## Idempotency And Audit

Idempotency uses the shared in-memory `make_idempotency_key` and `get_or_create` helpers. Checkout keys include operation, provider, order/product identifiers, amount, currency, payer identity, and return URL. Notify keys include operation, provider, order, transaction, notify id, amount, currency, and safe payload summary.

Audit uses the shared in-memory audit sink and records:

- `audit_id`
- `adapter`
- `operation`
- `mode`
- `idempotency_key`
- `side_effect_executed`
- `status`
- `error_code`
- `created_at`

## Side Effect Safety

D7.4 always reports:

- `real_product_write_executed=false`
- `real_wechat_pay_executed=false`
- `real_alipay_executed=false`
- `real_payment_notify_executed=false`
- `real_payment_provider_called=false`
- `side_effect_executed=false`

## API Compatibility

Commerce keeps the existing Product readonly API shape, Product fake write API shape, fake checkout API shape, and WeChat/Alipay transaction read shape. New `side_effect_safety` and `adapter_contract` metadata is additive.

Application boundaries:

- Product create/update/enable/disable/delete call `ProductWriteGateway`.
- WeChat checkout calls `WeChatPayAdapter`.
- Alipay checkout calls `AlipayAdapter`.
- WeChat/Alipay notify calls `PaymentNotifyGateway`.
- Alipay return calls `PaymentReturnGateway`.

## Payment Risk Notes

- Signing: signature verification methods exist, but real provider signing is not implemented in D7.4.
- Notify idempotency: fake notify uses deterministic idempotency and audit; future real notify must dedupe provider notify ids and transaction ids.
- Reconciliation: no reconciliation job is implemented; provider query methods are contract placeholders only.
- Amount and currency validation: fake checkout includes amount and currency in target and idempotency keys; future real calls must compare provider amount/currency against local order state.
- Order status transition: D7.4 builds order-status update previews and keeps real production state mutation out of scope.
- Rollback: disable adapter mode or revert the D7.4 boundary while legacy payment fallback remains retained.

## Next Steps

Next work should add provider sandbox-only implementations behind explicit flags, signature fixture tests, notify replay fixtures, reconciliation design, and human-approved payment canary evidence before any real external payment call.
