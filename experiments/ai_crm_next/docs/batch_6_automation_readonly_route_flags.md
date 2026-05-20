# Batch 6 Automation Readonly Route Flags

These route flags document the local dry-run or staging-simulated stance for Batch 6 Automation readonly. They must not be applied to production from this document.

## Dry-Run Flags

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=true
AICRM_NEXT_ROUTE_AUTOMATION_WRITES=false
AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK=false
AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME=false
AICRM_NEXT_AUTOMATION_AGENT_RUNTIME=false
AICRM_NEXT_EXTERNAL_OPENCLAW=false
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false
AICRM_NEXT_EXTERNAL_WEBHOOK=false
```

## Meaning

| flag | rehearsal value | meaning |
| --- | --- | --- |
| `AICRM_NEXT_ROUTE_AUTOMATION_READONLY` | true | Simulates selecting Next as readonly owner for Automation routes. |
| `AICRM_NEXT_ROUTE_AUTOMATION_WRITES` | false | Manual override, confirm conversion, silent/marketing writes remain out of scope. |
| `AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK` | false | Activation webhook remains disabled. |
| `AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME` | false | Workflow runtime remains disabled. |
| `AICRM_NEXT_AUTOMATION_AGENT_RUNTIME` | false | Agent runtime remains disabled. |
| `AICRM_NEXT_EXTERNAL_OPENCLAW` | false | Real OpenClaw push remains disabled. |
| `AICRM_NEXT_EXTERNAL_WECOM_DISPATCH` | false | Real WeCom dispatch remains disabled. |
| `AICRM_NEXT_EXTERNAL_WEBHOOK` | false | Real external webhook remains disabled. |

## Rollback

Dry-run rollback instruction:

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false
```

Expected route owner after rollback: old Flask.

## Safety Notes

- No production host or secret is included.
- No production proxy is modified.
- No real route cutover is executed.
- No old Flask write endpoint is executed.
- No manual override, confirm conversion, activation webhook, OpenClaw push, workflow runtime, agent runtime, WeCom dispatch, or external webhook is executed.
