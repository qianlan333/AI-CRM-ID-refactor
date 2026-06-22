# External Orders Enablement Acceptance

Date: 2026-06-22

## Goal

Prepare external order APIs for controlled enablement without changing
production env or committing secrets. The 90%+ readiness target is safe token
behavior, stable read shape, and order/customer/channel correlation evidence.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario external_orders_enablement \
  --order-no <optional_order_no>
```

For gray lifecycle readiness:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario external_orders_gray \
  --order-no <gray_order_no>
```

The diagnostic must keep:

- `real_external_call_executed=false`
- `production_write_executed=false`
- token values redacted

## Acceptance Cases

- Missing server token: controlled unavailable state is expected.
- Missing bearer token: request is rejected.
- Wrong bearer token: request is rejected.
- Correct bearer token: local order list/detail can be read.
- Unknown order: controlled not found.
- Duplicate gray order input: no duplicate business record should be created.
- Reconciliation: order/customer/channel/source and internal event/job state are
  visible in admin or diagnostic payloads.

## Production Preconditions

- `AUTOMATION_INTERNAL_API_TOKEN` configured by an authorized operator.
- Gray source approved.
- Token never appears in logs, docs, scripts, or PR body.

## Non-Goals

- No token creation in git.
- No production env edit.
- No real external provider call from this PR.

## Next Action

Run a separate gray acceptance PR after the operator configures token and gray
source credentials outside git.
