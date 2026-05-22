# Active Automation Re-enable Runbook

## Scope

This runbook covers the active automation timers that are still disabled:

- `aicrm-automation-jobs-run-due.timer`
- `aicrm-campaign-run-due.timer`

It does not enable timers, modify systemd/nginx/deploy config, remove legacy fallback, or execute real external calls.

## Recovery Order

### 1. Dry-run no-op

Call each Next-owned compatibility route with `dry_run=true` in the JSON body, query string, or `X-AICRM-Dry-Run=true`.

Required result:

- `side_effect_executed=false`
- `legacy_forwarded=false`
- no DB sentinel changes
- no WeCom, OpenClaw, agent runtime, webhook, or campaign dispatch call

### 2. Preview no-op

Call:

- `POST /api/admin/automation-conversion/jobs/run-due/preview`
- `POST /api/admin/cloud-orchestrator/campaigns/run-due/preview`

or pass `preview=true` to the existing run-due routes.

Required result:

- read-only response
- candidate IDs and risk flags returned
- no `automation_sop_batch`
- no `automation_workflow_execution`
- no `user_ops_send_records`
- no `outbound_tasks`
- no external calls

### 3. Bounded single execution with allowlist

Do not run a real active automation route unless the request includes an explicit allowlist and tight limits.

Automation jobs require:

- `allow_task_ids`, `allow_workflow_ids`, or `allow_node_ids`
- `max_send_records`
- `max_outbound_tasks`
- `operator`

Campaign jobs require:

- `allow_campaign_ids`
- `batch_size`
- `max_dispatch_count`

Production requests without an allowlist must fail with a 409/400 guardrail response.

### 4. Observe DB and logs

After any approved bounded execution, compare:

- `user_ops_send_records max(id)`
- `outbound_tasks max(id)`
- `automation_sop_batch max(id)`
- `automation_sop_batch_item max(id)`
- `automation_workflow_execution max(id)`
- `automation_workflow_execution_item max(id)`
- `automation_operation_task_execution max(id)`
- `automation_operation_task_execution_item max(id)`

Also review application logs for any external dispatch attempt.

### 5. Enable timer only after evidence

Only enable the disabled timers after:

- dry-run checker passes
- preview checker passes
- bounded single execution is approved and observed
- logs and DB sentinels are reviewed
- human operator signs off

## Validation

Run:

```bash
python3 tools/check_active_automation_run_due_guardrails.py \
  --output-md /tmp/active_automation_guardrails.md \
  --output-json /tmp/active_automation_guardrails.json
```

The checker must pass before moving from dry-run to preview or bounded execution.
