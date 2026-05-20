# Automation Readonly Sample And Fake Checklist

This checklist keeps Automation readonly gray preparation separate from workflow execution. It does not authorize production cutover or real external calls.

## Readonly Gray Boundary

- Readonly gray does not require executing real workflow writes.
- Default smoke sends only `GET` requests.
- Old Flask, when supplied through `--old-base-url`, receives only `GET`.
- No activation webhook, OpenClaw push, WeCom dispatch, external webhook, workflow runtime, or agent runtime is executed.

## Minimum Data Expectations

| area | minimum sample | why it matters | if missing |
| --- | --- | --- | --- |
| overview | any automation members sufficient to render cards | validates overview card shape | shape-only pass is acceptable if response keys exist |
| pools | six-pool definitions and counts | validates pool display contract | missing required pool item keys is a blocker |
| members list | at least one member with `member_id` | enables member detail smoke | detail route is skipped with `missing_member_id` |
| member detail | one `member_id` selected from members list | validates detail, history, and customer-context shape | full readonly gray evidence is incomplete |
| execution records | zero or more records with list envelope | validates readonly execution projection | empty list is acceptable if envelope keys exist |

## Six-Pool State Display

The readonly page and pools API should preserve the six-pool state display expected by the Automation Conversion parity strategy. Counts may differ across fixtures, local test DBs, and old Flask, but Next must keep required pool item fields:

- `pool_key`
- `label`
- `count`
- `description`
- `active_action_count`
- `allow_broadcast`

## Fake Write Boundary

Fake writes are optional and only allowed with:

```bash
.venv/bin/python tools/automation_readonly_gray_smoke.py \
  --next-testclient \
  --include-fake-writes \
  --output-md /tmp/automation_readonly_gray_smoke_with_fake_writes.md \
  --output-json /tmp/automation_readonly_gray_smoke_with_fake_writes.json
```

Allowed fake-write checks are limited to Next TestClient fixture state:

- override followup type
- confirm conversion
- enter silent
- exit marketing

Still forbidden in fake-write mode:

- OpenClaw push
- activation webhook
- real workflow runtime
- real agent runtime
- WeCom dispatch
- external webhook
- old Flask writes

## Fake External Adapter Boundary

| adapter | current boundary | production requirement |
| --- | --- | --- |
| OpenClaw | fake / disabled in readonly gray | real adapter contract, retry/audit/idempotency, and no unintended push |
| WeCom | fake / disabled in readonly gray | real dispatch tests, media tests, and side-effect audit |
| activation webhook | excluded from readonly gray | webhook signing/idempotency/audit and rollback plan |
| workflow runtime | not executed | runtime phase 2, queue safety, idempotency, and observability |

## Old Flask Missing Data

If old Flask lacks comparable automation read routes or member samples, dual mode may record:

- `legacy_missing_read_route` when old returns 404/405 and Next satisfies the scoped readonly contract.
- `missing_member_id` when member detail cannot safely be sampled.

These are not production readiness. They mean the local test environment needs masked automation sample data before claiming full old-vs-new parity for sample-dependent routes.

## Local Masked Seed Tool

Seed tool:

```bash
.venv/bin/python tools/seed_old_flask_automation_sample.py \
  --database-url "$OLD_FLASK_TEST_DATABASE_URL" \
  --apply
```

Safety guard:

- Host must be `localhost`, `127.0.0.1`, or `::1`.
- Database name must be exactly `aicrm_old_flask_test` and include `test`.
- Default mode is dry-run; writes require explicit `--apply`.
- The tool prints only a redacted database URL.
- The tool does not import `wecom_ability_service` or `openclaw_service`.
- The seeded workflow is disabled and marked as a local masked sample; it does not trigger workflow runtime.

## Masked Sample Rules

If later seed data is needed, use only local test databases and masked values:

- `member_id`: `automation_member_masked_001`
- `external_userid`: `external_user_masked_automation_001`
- `mobile`: `mobile_masked_automation_001`
- `customer_name`: `customer_masked_automation_001`
- `owner_userid`: `owner_masked_automation_001`

Do not use real customer names, phone numbers, `external_userid`, OpenClaw payloads, or WeCom identifiers.

## 2026-05-20 Local Sample Evidence

The local old Flask test database `aicrm_old_flask_test` was seeded with:

- `external_userid`: `external_user_masked_automation_001`
- `customer_name`: `customer_masked_automation_001`
- `mobile`: `mobile_masked_automation_001`
- `owner_userid`: `owner_masked_automation_001`
- `member_external_id`: `automation_member_masked_001`
- `execution_id`: `automation_execution_masked_001`
- `workflow_code`: `automation_workflow_masked_001`

Readonly old Flask API verification after seeding:

| old readonly check | result | notes |
| --- | --- | --- |
| `GET /api/admin/automation-conversion/dashboard` | 200 | Used as old alias for Next overview and pools. |
| `GET /api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50` | 200 | Returned the masked member sample. |
| `GET /api/admin/automation-conversion/member?external_contact_id=external_user_masked_automation_001` | 200 | Returned masked member detail. |
| `GET /api/admin/automation-conversion/executions` | 200 | Returned masked execution evidence. |

Dual smoke report:

- Markdown: `/tmp/automation_readonly_gray_smoke_dual_after_sample.md`
- JSON: `/tmp/automation_readonly_gray_smoke_dual_after_sample.json`
- Result: `ok=true`, `compared=6`, `failed=0`, `blockers=0`, `skipped=1`.
- Remaining skip: `fake_writes_not_requested`, which is expected for default readonly dual mode.
- Route warnings are legacy drift from old admin auth redirect and old alias payload shapes, not Next contract blockers.
