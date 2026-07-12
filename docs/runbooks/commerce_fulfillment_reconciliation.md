# Commerce Fulfillment Reconciliation Runbook

This command diagnoses payment/refund/entitlement continuation gaps without exposing contact data or calling a provider:

```bash
python scripts/ops/reconcile_commerce_fulfillment.py
```

Deployment runs exactly this count-only form. It reports:

- `paid_without_payment_outbox`
- `paid_service_product_without_entitlement_or_open_consumer`
- `successful_full_refund_with_active_entitlement`
- `refund_request_without_effect`
- `duplicate_order_paid_effect`
- `legacy_domain_outbox_pending`

Output contains counts and at most 20 numeric internal IDs per class. It does not include mobile, unionid, openid, external_userid, webhook payloads, questionnaire answers, or messages. Confirm `database_mutation_performed=false`, `consumer_executed=false`, `real_external_call_executed=false`, and `pii_in_output=false`.

## Safe continuation repair

Repair requires an auditable actor and reason:

```bash
python scripts/ops/reconcile_commerce_fulfillment.py \
  --repair \
  --actor "$OPERATOR" \
  --reason "approved durable continuation recovery" \
  --limit 100
```

Repair may only ensure idempotent `payment.succeeded` or `refund.succeeded` outbox rows. It stores a hash of the actor and the reason in outbox summary metadata. It does not relay outbox rows, run consumers, edit entitlement state directly, create/refire refund provider jobs, or dispatch External Effects.

After repair, run count-only mode again, inspect internal-event queue state, and let the normal workers process approved due work. `refund_request_without_effect`, duplicate effects, and legacy outbox backlog require investigation; this repair command intentionally does not manufacture or dispatch provider work.

## Incident pause and rollback

For incorrect or uncertain provider state, stop the canonical internal-event and external-effect worker timers. Preserve outbox and jobs, follow R07 unknown-after-dispatch reconciliation, and fix forward. Never restart `openclaw-external-push-worker.timer` or `.service`; both are retired-forbidden.
