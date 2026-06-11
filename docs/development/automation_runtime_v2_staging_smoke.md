# Automation Runtime v2 Staging Smoke

This runbook validates Automation Runtime v2 on staging after the legacy Flask
HTTP/runtime archive. It does not replace frontend click acceptance, and it must
not be run against production as staging evidence.

## Safety Boundary

- Do not start the broadcast worker for this smoke.
- Do not real-send WeCom messages.
- Only smoke test data and `broadcast_jobs` rows may be written.
- Smoke data must use the `smoke_runtime_v2` prefix.
- Cleanup must run with the emitted `smoke_run_id`.

## Required Queue Isolation

Before running the smoke, pause the staging worker timer using the staging
operations convention, for example:

```bash
systemctl --user stop aicrm-broadcast-queue-worker.timer
systemctl --user is-active aicrm-broadcast-queue-worker.timer
```

The timer must be inactive before acceptance. The smoke harness checks for
recent `automation_runtime_v2` worker activity and fails the run if smoke jobs
are claimed while scenarios are executing.

## Remote App Smoke

```bash
python scripts/smoke_automation_runtime_v2.py \
  --database-url "$STAGING_DATABASE_URL" \
  --app-url "$STAGING_APP_URL" \
  --admin-cookie "$ADMIN_COOKIE" \
  --scenario all \
  --allow-write
```

All seven scenarios must pass:

- `channel-binding`
- `large-channel-protection`
- `future-scan`
- `questionnaire-agent`
- `payment`
- `webhook`
- `scheduled`

## Cleanup

```bash
python scripts/smoke_automation_runtime_v2.py \
  --database-url "$STAGING_DATABASE_URL" \
  --cleanup \
  --smoke-run-id "<smoke_run_id>"
```

Cleanup only cancels smoke-scoped queued, pending, planned, or un-dispatched
claimed jobs and marks smoke task plans cancelled. It does not physically delete
real memberships.

After cleanup, restore the staging worker timer if it was active before the run.
