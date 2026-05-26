# Phase 5Z Payment Commerce Adapter Contract + Fake Stub

## Status

- phase_5z_payment_commerce_adapter_contract_fake_stub
- contract and fake/stub readiness only
- no real payment capture
- no refund
- no settlement
- no production payment webhook cutover
- no production order state mutation
- no raw secret or token output
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- delete_ready false

## Contract Scope

This bundle covers payment/commerce adapter contract and fake/stub evidence for `/api/admin/wechat-pay*`:

- create payment intent contract
- query payment status contract
- refund request contract shape
- webhook verification contract
- fake webhook evidence
- idempotency / replay / conflict policy
- order/payment dry-run state evidence
- error mapping

It does not implement real provider capture, refund, settlement, webhook cutover, order mutation, or secret persistence.

## Fake/Stub Behavior

Fake mode returns deterministic payment intent, status, refund, and webhook evidence. It does not call a provider, does not read payment secrets, does not mutate production orders, and does not claim real financial success.

## Error Mapping

- payment_config_missing
- payment_signature_invalid
- idempotency_key_required
- duplicate_idempotency_key
- order_id_missing
- amount_invalid
- currency_unsupported
- real_payment_not_enabled
- refund_not_enabled
- webhook_cutover_not_enabled
- forbidden_in_production_without_approval

## Idempotency / Replay

Write-like dry-runs require an idempotency key. Same key plus same request hash returns replay evidence. Same key plus different payload returns conflict. No partial external or financial side effect is possible in this bundle because all real provider behavior is disabled.

## Evidence Policy

Evidence includes adapter mode, real payment executed false, refund executed false, settlement executed false, webhook cutover executed false, production order mutation executed false, idempotency key, request hash, redacted order/customer references, result status, side-effect safety, and timestamp.

## Next Recommendation

Stop after this bundle for this run. A later bundle may add payment live adapter code behind explicit flags, but real capture/refund/settlement and production webhook cutover require separate approval and must remain default blocked.
