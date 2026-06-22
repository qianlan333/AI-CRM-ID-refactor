# WeCom Auth And Callback Operator Acceptance

Date: 2026-06-22

## Goal

Define readiness for WeCom operator auth and callback gray validation without
enabling real token exchange or committing callback secrets.

## Diagnostics

Operator auth readiness:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_auth_operator
```

Callback gray readiness:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_callback_gray \
  --receiver-token <redacted-test-receiver-token>
```

Both diagnostics must report:

- `real_external_call_executed=false`
- `production_write_executed=false`
- configured env values redacted

## Acceptance Cases

- Auth start route is reachable.
- Callback missing code returns controlled failure.
- Invalid state returns controlled failure.
- Token exchange remains blocked unless separately approved.
- Invalid callback signature creates no job.
- Duplicate callback reuses the idempotency key.
- Accepted callback is traceable to event/job status.

## Production Preconditions

- `WECOM_CORP_ID`
- `WECOM_AGENT_ID`
- `ADMIN_LOGIN_REDIRECT_URI`
- `WECOM_CONTACT_SECRET` for contact callback gray validation
- approved test operator / receiver scope

## Non-Goals

- No raw external_userid committed.
- No WeCom secret committed.
- No production deploy/systemd/nginx/env modification.
- No broad callback migration in this PR.

## Next Action

Run the operator-owned gray acceptance only after auth/callback configuration is
approved outside git.
