# Ops Plan To Broadcast E2E Acceptance

Date: 2026-06-22

## Goal

Prove the event / approval / task loop can be explained from plan approval to
Push Center visibility. This document defines acceptance for
`ops_plan.approved` or equivalent approval events without changing runtime
worker behavior.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario ops_plan_to_broadcast \
  --plan-id <plan_id> \
  --event-id <internal_event_id>
```

The diagnostic is dry-run by default and must not dispatch workers or external
effects. It checks readiness for:

- internal event creation/reuse
- consumer-run visibility
- generated broadcast/external-effect job correlation
- Push Center reconciliation

## Acceptance Cases

- Positive: one approval produces or reuses one internal event, one consumer run,
  and one expected business job/effect.
- Duplicate: repeated approval reuses the idempotency key and does not duplicate
  jobs.
- Failure: missing config, invalid target, downstream job create failure, and
  worker exception have distinct reasons.
- Retry: only the failed consumer/job is retried, with operator audit context.

## Operator Explanation Fields

The final E2E evidence should expose:

- `derived_status`
- `pending_reason`
- `effect_job_status`
- `retryable`
- `operator_action_required`
- `next_action_label`
- `linked_push_center_job`

## Non-Goals

- No production migration.
- No direct DB inspection requirement for the operator.
- No real WeCom/Payment/OAuth external call.

## Next Action

Add an event business explanation payload if any of the fields above are missing
from the current admin/event details.
