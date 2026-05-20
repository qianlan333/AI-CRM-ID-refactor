# Batch 6 Automation Readonly Canary Execution Report

This report records a staging-simulated canary execution for Batch 6 Automation readonly. It is not a production rollout and did not modify production proxy, Nginx, deploy, or route configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `automation_readonly` |
| execution mode | `staging_simulated_canary` |
| operator | Codex |
| timestamp | 2026-05-20 20:54:56 CST |
| git commit | `d48082a` |
| old service target | `http://127.0.0.1:5001` GET-only with documented route aliases when available |
| next target | AI-CRM Next TestClient |
| staging proxy target | not available / not used |
| database target | AI-CRM Next fixture/in-memory TestClient data plus old local test DB GET-only alias comparison |
| external adapters mode | fake / disabled |
| manual override executed | no |
| confirm conversion executed | no |
| silent / exit writes executed | no |
| activation webhook executed | no |
| OpenClaw push executed | no |
| workflow runtime executed | no |
| agent runtime executed | no |
| WeCom dispatch executed | no |
| external webhook executed | no |
| production traffic cut | no |
| production config modified | no |

## Route Flags

Staging-only flag stance used for this simulated canary:

```bash
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=true
AICRM_NEXT_ROUTE_AUTOMATION_WRITES=false
AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK=false
AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME=false
AICRM_NEXT_AUTOMATION_AGENT_RUNTIME=false
AICRM_NEXT_EXTERNAL_OPENCLAW=false
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false
AICRM_NEXT_EXTERNAL_WEBHOOK=false
```

These flags were not written to production config and were not committed as a real `.env`.

## Included Routes

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `GET /api/admin/automation-conversion/execution-records`

## Excluded Routes

- `POST /api/admin/automation-conversion/members/{member_id}/override-followup-type`
- `POST /api/admin/automation-conversion/members/{member_id}/confirm-conversion`
- `POST /api/admin/automation-conversion/members/{member_id}/enter-silent`
- `POST /api/admin/automation-conversion/members/{member_id}/exit-marketing`
- `POST /api/admin/automation-conversion/members/{member_id}/push-openclaw-context`
- `POST /api/customer-automation/activation-webhook`
- workflow / agent runtime write routes
- WeCom dispatch routes
- external webhook routes
- old system writes

## Pre-Check Evidence

| check | report | result |
| --- | --- | --- |
| Automation readonly gray smoke | `/tmp/automation_readonly_gray_smoke_batch_6.json` | PASS with accepted legacy route drift |
| Automation parity | `/tmp/automation_parity_batch_6.json` | PASS |
| readiness checker | `/tmp/batch_6_automation_canary_readiness.json` | `canary_plan_ready` / `GO_TO_STAGING_CANARY_SIGNOFF` |
| screenshot baseline | `artifacts/frontend_screenshots/route_status.json` | `/admin/automation-conversion` route present and passing |
| real PostgreSQL integration | `docs/real_postgres_integration_run.md` | evidence available |

## Canary Smoke Result

Command:

```bash
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=true \
AICRM_NEXT_ROUTE_AUTOMATION_WRITES=false \
AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK=false \
AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME=false \
AICRM_NEXT_AUTOMATION_AGENT_RUNTIME=false \
AICRM_NEXT_EXTERNAL_OPENCLAW=false \
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false \
AICRM_NEXT_EXTERNAL_WEBHOOK=false \
.venv/bin/python tools/automation_readonly_gray_smoke.py \
  --old-base-url http://127.0.0.1:5001 \
  --next-testclient \
  --output-md /tmp/automation_readonly_gray_smoke_batch_6.md \
  --output-json /tmp/automation_readonly_gray_smoke_batch_6.json
```

Result: PASS with accepted legacy route drift.

## Dual Smoke Result

The Automation readonly gray smoke dual mode is the Batch 6 dual evidence. It sends old Flask only GET requests and uses documented old route aliases where the exact Next-style old route is missing. It never sends manual override, confirm conversion, enter/exit, activation webhook, OpenClaw push, workflow runtime, agent runtime, WeCom dispatch, external webhook, or old write routes.

## Legacy Drift

- old `/admin/automation-conversion` may redirect unauthenticated users with `302 /login`, accepted as `legacy_admin_auth_redirect` when Next page route is 200.
- old exact Next-style readonly API paths can return 404; documented old route aliases are used for GET-only evidence.
- old alias payload shapes differ from the Next readonly contract; this is accepted only when Next satisfies the required shape.

## Side-Effect Safety

| safety flag | result |
| --- | --- |
| `old_write_endpoints_executed` | false |
| `openclaw_push_executed` | false |
| `wecom_dispatch_executed` | false |
| `external_webhook_executed` | false |
| `activation_webhook_executed` | false |
| `workflow_runtime_executed` | false |
| `next_fake_writes_executed` | false |
| `production_config_modified` | false |
| `real_traffic_cutover_executed` | false |
| `default_endpoints_get_only` | true |

## Rollback Dry-Run

Rollback is simulated only because no real staging proxy route is changed.

- rollback instruction: `AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false`
- owner after rollback: old Flask
- rollback verification: dry-run only
- production config modified: false
- real route changed: false

## Blockers

None.

## Warnings

- accepted legacy drift: old admin auth redirect.
- accepted legacy drift: old route alias / legacy payload shape differences.

## Skipped

- `fake_writes_not_requested`: expected for Batch 6 readonly.
- real staging proxy rollback: skipped because execution mode is `staging_simulated_canary`.

## Recommendation

GO for staging-simulated canary evidence.

This does not approve production rollout. A real staging proxy canary still requires operator signoff, staging route-owner confirmation, and rollback observation before any production canary.

## Signoff Status

`staging_simulated_only`

## Next Action

Run Batch 6 Automation readonly canary against an actual staging proxy or staging base URL with the same GET-only route scope and rollback owner.
