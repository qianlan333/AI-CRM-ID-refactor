# Phase 5AA Payment Commerce Live Adapter Behind Flag

## Status

- phase_5aa_payment_commerce_live_adapter_behind_flag
- live adapter code implemented behind explicit flags
- live adapter disabled by default
- sandbox mode required by default
- no real payment capture
- no real refund
- no real settlement
- no production payment webhook cutover
- no production order state mutation
- no raw payment secret or token output
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- delete_ready false

## Live Adapter Gates

The payment live adapter boundary only returns blocked or sandbox-gate evidence unless every gate is present:

- AICRM_PAYMENT_COMMERCE_LIVE_ADAPTER_ENABLED
- AICRM_PAYMENT_COMMERCE_LIVE_CALL_APPROVED
- AICRM_PAYMENT_COMMERCE_PROVIDER_CONFIG_REVIEWED
- AICRM_PAYMENT_COMMERCE_SANDBOX_MODE_APPROVED
- AICRM_PAYMENT_COMMERCE_NO_MONEY_MOVEMENT_CONFIRMED
- AICRM_PAYMENT_COMMERCE_PROVIDER_NAME
- AICRM_PAYMENT_COMMERCE_PROVIDER_SECRET, redacted and never printed
- idempotency key
- explicit no-money-movement confirmation in runner or adapter invocation

The gateway is a disabled provider boundary in this bundle. It records request hash, idempotency evidence, and side-effect safety, but it does not execute capture, refund, settlement, webhook cutover, or order mutation.

## Implemented Boundary

- create_payment_intent_live
- query_payment_status_live
- request_refund_live, blocked with refund_not_enabled
- verify_payment_webhook_live, shape only and blocked with webhook_cutover_not_enabled

## Staging Evidence

The staging evidence runner supports dry-run gate checks and an explicitly gated sandbox staging path. The default run is blocked. Even with approvals, the gateway remains no-money-movement and disabled in this bundle.

## Production Dry-Run Gate

The production dry-run gate never calls a payment provider and never mutates orders. It only checks that the no-production-provider-call, no-money-movement, no-order-mutation, and no-webhook-cutover confirmations are present.

## Idempotency Policy

Write-like live-gate operations require an idempotency key. Same key plus same request hash returns replay evidence. Same key plus different payload returns duplicate_idempotency_key conflict. Blocked requests are retry-safe because there is no provider call and no financial or production side effect.

## Evidence Policy

Evidence includes adapter mode, live adapter gate status, provider config review status, sandbox mode status, idempotency key, request hash, redacted order or payment reference, provider secret redaction, result status, side-effect safety, and timestamp.

## Production Behavior

Production behavior is unchanged. This bundle does not change payment routes, webhook ownership, production order state, fallback, or production_compat.

## Phase 5AB Recommendation

Next: phase_5ab_payment_commerce_staging_sandbox_canary_evidence_bundle for staging/sandbox canary evidence. It must continue to forbid real capture, refund, settlement, production order mutation, and production webhook cutover.
