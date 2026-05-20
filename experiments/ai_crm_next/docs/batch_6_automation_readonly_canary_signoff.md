# Batch 6 Automation Readonly Canary Signoff Draft

This signoff draft is based on `docs/gray_release_signoff_template.md`. It records staging-simulated evidence only and does not approve production rollout.

| field | value |
| --- | --- |
| batch name | `automation_readonly` |
| operator | Codex |
| timestamp | 2026-05-20 20:54:56 CST |
| git commit | `d48082a` |
| old service version | local old Flask GET-only alias target when available |
| next service version | AI-CRM Next TestClient |
| database target | fixture/in-memory TestClient data plus old local test DB GET-only alias comparison |
| external adapters mode | fake / disabled |
| canary mode | `staging_simulated_canary` |
| staging proxy | not available / not used |
| smoke result | `/tmp/automation_readonly_gray_smoke_batch_6.json` |
| parity result | `/tmp/automation_parity_batch_6.json` |
| dual smoke result | Automation readonly gray smoke dual report |
| readiness result | `/tmp/batch_6_automation_canary_readiness.json` |
| legacy drift accepted | old route aliases / `legacy_missing_read_route`; old admin auth redirect |
| screenshot baseline link | `artifacts/frontend_screenshots/route_status.json` |
| rollback owner | old Flask |
| rollback instruction | `AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false` |
| rollback status | dry-run only; no real route changed |
| go/no-go decision | GO for staging-simulated canary evidence |
| signoff status | `staging_simulated_only` |

## Risk Acceptance

Accepted for staging-simulated evidence:

- No production proxy or deployment config is modified.
- No production traffic is switched.
- No old-system write endpoint is executed.
- No manual override, confirm conversion, enter-silent, or exit-marketing route is executed.
- Activation webhook is not executed.
- OpenClaw push is not executed.
- Workflow runtime and agent runtime are not executed.
- Real WeCom dispatch is not executed.
- External webhook is not executed.
- Old route alias/shape drift is accepted only when Next satisfies the Automation readonly contract.
- Old admin auth redirect is accepted only as legacy page/auth drift.

Not accepted:

- Production rollout.
- Production Nginx/app route changes.
- Automation write route cutover.
- Activation webhook route cutover.
- OpenClaw push enablement.
- Workflow or agent runtime enablement.
- Real WeCom dispatch.
- Real external webhook push.

## Required Human Signoff Before Real Staging Proxy Canary

| role | signoff |
| --- | --- |
| release owner | pending |
| product owner | pending |
| rollback owner | pending |
| staging operator | pending |

## Next Action

Execute the same Batch 6 GET-only canary against a real staging proxy or staging base URL, then update this signoff with real staging route-owner and rollback evidence.
