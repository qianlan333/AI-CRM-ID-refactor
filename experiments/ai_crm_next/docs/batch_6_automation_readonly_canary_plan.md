# Batch 6 Automation Readonly Canary Plan

This plan prepares a staging or production-like canary for Batch 6 Automation Conversion readonly. It does not switch production routes, execute automation writes, run activation webhooks, push OpenClaw context, run workflow/agent runtime, call real WeCom dispatch, send external webhooks, or modify production proxy/deploy configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `automation_readonly` |
| production rollout | not approved |
| automation writes | excluded |
| activation / workflow / agent runtime | excluded |
| external OpenClaw / WeCom / webhook | fake / disabled |
| accepted legacy drift | old route alias / `legacy_missing_read_route`; old admin page unauthenticated `legacy_admin_auth_redirect` |

## Execution Mode Options

| mode | allowed use | notes |
| --- | --- | --- |
| `staging_simulated` | AI-CRM Next TestClient plus old Flask GET-only alias smoke evidence | No route owner changes. |
| `staging_proxy` | Staging proxy/router only | Requires rollback owner and staging operator signoff. |
| `header_allowlist` | One operator/session in staging | Route only requests with canary header. |
| `cookie_allowlist` | One operator/session in staging | Route only requests with canary cookie. |

## Included Readonly Routes

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `GET /api/admin/automation-conversion/execution-records`

## Excluded Operations

- manual override
- confirm conversion
- enter silent
- exit marketing
- activation webhook
- OpenClaw push
- workflow runtime
- agent runtime
- WeCom dispatch
- external webhook
- old system writes
- production route cutover

## Entry Criteria

| criterion | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| six parity pass | all `tools/compare_*_parity.py` reports |
| Automation parity pass | `tools/compare_automation_conversion_parity.py` |
| Automation readonly gray smoke pass | `tools/automation_readonly_gray_smoke.py --old-base-url ... --next-testclient` |
| Automation dual smoke pass | dual smoke has only accepted legacy route drift |
| real PostgreSQL integration evidence available | `docs/real_postgres_integration_run.md` |
| PNG screenshot baseline pass | `artifacts/frontend_screenshots/route_status.json` includes `/admin/automation-conversion` |
| no old production entrypoint dirty | `git status --short --untracked-files=all` review |
| no production config modified | deploy/production config status scan and side-effect report |
| accepted legacy drift documented | old route aliases / `legacy_missing_read_route`; old admin auth redirect |

## Exit Criteria

- readonly Automation routes return 200 on Next
- old route aliases and route drift are documented
- member detail sample is available or any missing sample is explicitly recorded
- forbidden placeholders remain absent through frontend screenshot baseline
- side-effect safety flags are all false
- rollback dry-run is verified
- signoff draft is complete
- no write, external, webhook, workflow, or agent runtime route appears in default canary route results

## No-Go Conditions

- any automation write route executed
- activation webhook executed
- OpenClaw push executed
- workflow runtime executed
- agent runtime executed
- WeCom dispatch executed
- external webhook executed
- production config modified
- old service write endpoint called
- smoke blocker
- parity blocker
- missing rollback owner
- Next missing required automation readonly shape

## Readiness Command

```bash
.venv/bin/python tools/check_batch_6_automation_canary_readiness.py \
  --automation-smoke-json /tmp/automation_readonly_gray_smoke_batch_6.json \
  --automation-parity-json /tmp/automation_parity_batch_6.json \
  --output-md /tmp/batch_6_automation_canary_readiness.md \
  --output-json /tmp/batch_6_automation_canary_readiness.json
```

## Conclusion

Batch 6 readiness can only reach `canary_plan_ready` or `staging_simulated_canary_pass`. It is not `production_ready` and does not approve manual override, confirm conversion, activation webhook, OpenClaw push, workflow runtime, agent runtime, WeCom dispatch, external webhook calls, automation writes, or production route cutover.
