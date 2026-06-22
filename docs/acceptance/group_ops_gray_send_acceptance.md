# Group Ops Gray Send Acceptance

Date: 2026-06-22

## Goal

Validate the Group Ops send loop at 90%+ trial-operation readiness without
defaulting to real outbound sends. The acceptance path starts with a dry-run
diagnostic and only permits operator-owned gray execution after explicit receiver
and environment approval.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send
```

The script must report:

- `dry_run=true`
- `real_external_call_executed=false`
- `production_write_executed=false`
- required approval env names, redacted when configured
- Push Center reconciliation route coverage

An operator may request readiness for gray execution with `--execute`, but the
script still performs no external call. It only returns
`operator_execute_allowed=true` when:

- `AICRM_GROUP_OPS_GRAY_SEND_APPROVED` is configured.
- `AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST` is configured.
- `--receiver-token` is supplied and redacted in output.

## Acceptance Cases

- Positive dry-run: plan, webhook route, external effect job, worker, attempt,
  and Push Center reconciliation are all named before any real receiver action.
- Failure: missing approval/env/receiver blocks operator execution readiness.
- Retry/compensation: failed jobs must be inspected through
  `/api/admin/push-center/jobs/{job_id}/reconciliation` before retry.
- Reconciliation: shadow failure must not be counted as business failure if the
  main broadcast job succeeded.

## Non-Goals

- No real WeCom send by default.
- No production deploy/systemd/nginx/env modification.
- No receiver identifier committed to git.
- No UI redesign.

## Next Action

After this dry-run acceptance is merged, run an approved gray-send PR with a
separate operator-owned evidence record.
