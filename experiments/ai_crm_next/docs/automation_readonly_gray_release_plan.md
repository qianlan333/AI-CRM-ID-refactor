# Automation Readonly Gray Release Plan

This plan prepares Automation Conversion for a future route-level readonly gray release. It is not a production cutover, does not execute workflow runtime, and does not call real OpenClaw, WeCom, or external webhooks.

## Scope

Readonly routes in scope:

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `GET /api/admin/automation-conversion/execution-records`

## Current Status

| area | status | notes |
| --- | --- | --- |
| frontend | partial adapter | The admin page is covered by the route-level smoke/screenshot baseline. No UI redesign is part of this phase. |
| backend | parity-ready partial | Overview, pools, members, member detail, execution records, and fake state transitions are covered by contract/parity tests. |
| state machine | partial | Six-pool display and fixture-backed transitions exist; workflow runtime phase 2 is not complete. |
| database | fixture / in-memory | Automation Conversion is not connected to production PostgreSQL. |
| external adapter | OpenClaw fake, WeCom fake, webhook fake | Real OpenClaw push, WeCom dispatch, and external webhook execution are disabled/out of scope. |
| production replacement | not ready | No production route cutover, production data migration, workflow runtime, or real external adapter validation exists. |

## Gray-Eligible Items

- Automation Conversion admin page readonly smoke.
- Overview API shape.
- Pools API shape.
- Members list API shape.
- Member detail API shape using a sample `member_id` from the members list.
- Execution records readonly shape.
- Six-pool state display.
- Screenshot baseline for `/admin/automation-conversion`.
- Automation fixture parity.

## Not Gray-Eligible

- Manual override writes against old Flask or production.
- Confirm conversion writes against old Flask or production.
- Enter/exit silent writes against old Flask or production.
- Activation webhook writes.
- OpenClaw context push.
- Real workflow runtime.
- Real agent runtime.
- Real WeCom dispatch.
- External webhook execution.
- Production data migration/backfill.
- Production write route cutover.

## Fake State-Machine Writes

`tools/automation_readonly_gray_smoke.py --include-fake-writes` may execute fixture-backed state-machine writes only against AI-CRM Next TestClient. It does not call old Flask and does not execute OpenClaw push, activation webhook, workflow runtime, or real WeCom dispatch.

Default smoke never includes fake writes.

## Local Old-Flask Alias And Sample Evidence

Old Flask does not expose several Automation readonly routes under the same names as the AI-CRM Next contract. The documented readonly aliases are:

| Next route | old Flask readonly alias | status after local masked sample |
| --- | --- | --- |
| `/api/admin/automation-conversion/overview` | `/api/admin/automation-conversion/dashboard` | old 200 / Next 200 |
| `/api/admin/automation-conversion/pools` | `/api/admin/automation-conversion/dashboard` | old 200 / Next 200 |
| `/api/admin/automation-conversion/members` | `/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50` | old 200 / Next 200 |
| `/api/admin/automation-conversion/members/{member_id}` | `/api/admin/automation-conversion/member?external_contact_id=external_user_masked_automation_001` | old 200 / Next 200 |
| `/api/admin/automation-conversion/execution-records` | `/api/admin/automation-conversion/executions` | old 200 / Next 200 |

The local test database `aicrm_old_flask_test` has masked seed evidence from `tools/seed_old_flask_automation_sample.py`. The follow-up dual report `/tmp/automation_readonly_gray_smoke_dual_after_sample.json` passed with `blockers=0`; the remaining default skip is `fake_writes_not_requested`. Legacy warnings are expected because old aliases use old payload shapes and the old admin page redirects unauthenticated requests to login.

## Preconditions

| condition | required evidence |
| --- | --- |
| Ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| Automation parity pass | `tools/compare_automation_conversion_parity.py --old-fixture-dir ... --next-testclient` |
| Frontend smoke pass | `tests/test_frontend_route_smoke.py` and screenshot baseline |
| Screenshot baseline pass | `docs/frontend_screenshot_baseline.md` and `artifacts/frontend_screenshots/` |
| No old backend imports | boundary scan over `experiments/ai_crm_next` |
| No old write endpoints | gray smoke side-effect safety flags remain false |
| No real OpenClaw / WeCom / webhook calls | fake/disabled adapters only |
| Rollback checklist ready | route-level rollback to old Flask documented below |

## Rollback

1. Keep old Automation Conversion routes active during preparation.
2. Route-level rollback sends `/admin/automation-conversion` and readonly Automation API traffic back to old Flask.
3. Disable the Next automation readonly route flag.
4. Do not run destructive operations during preparation.
5. Re-run readonly smoke after rollback to verify old Flask route availability.

## Go / No-Go

Go only when:

- Ordinary pytest passes.
- Automation parity passes.
- Automation readonly gray smoke passes in default GET-only mode.
- Optional fake-write smoke passes only against Next TestClient.
- Frontend screenshot baseline includes `/admin/automation-conversion`.
- No old backend imports exist in AI-CRM Next.
- `old_write_endpoints_executed=false`.
- `openclaw_push_executed=false`.
- `wecom_dispatch_executed=false`.
- `external_webhook_executed=false`.
- `activation_webhook_executed=false`.
- `workflow_runtime_executed=false`.

No-Go if:

- Any write/external endpoint is included in default smoke.
- Old Flask receives POST/PUT/PATCH/DELETE.
- OpenClaw push, WeCom dispatch, external webhook, activation webhook, workflow runtime, or agent runtime executes.
- Any required readonly API shape key is missing in Next.
- Any route is mislabeled `production_ready`.
- Production route cutover is attempted.

## Next Action

Run Automation full readonly dual-run acceptance against the archived after-sample report. Do not proceed to production route-level execution until that acceptance confirms no blockers, no old writes, and no real OpenClaw/WeCom/webhook/workflow runtime effects.
