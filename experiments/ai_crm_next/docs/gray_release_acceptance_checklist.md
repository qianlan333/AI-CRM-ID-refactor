# Gray Release Acceptance Checklist

This checklist must be completed for every route-level gray batch. It does not authorize production cutover by itself.

## Global Commands

```bash
.venv/bin/python -m pytest -q
```

Run all six parity tools:

```bash
.venv/bin/python tools/compare_user_ops_parity.py --old-fixture-dir tests/fixtures/old_user_ops --next-testclient --output-md /tmp/user_ops_parity_gray.md --output-json /tmp/user_ops_parity_gray.json
.venv/bin/python tools/compare_customer_read_model_parity.py --old-fixture-dir tests/fixtures/old_customer_read_model --next-testclient --output-md /tmp/customer_parity_gray.md --output-json /tmp/customer_parity_gray.json
.venv/bin/python tools/compare_questionnaire_parity.py --old-fixture-dir tests/fixtures/old_questionnaire --next-testclient --output-md /tmp/questionnaire_parity_gray.md --output-json /tmp/questionnaire_parity_gray.json
.venv/bin/python tools/compare_commerce_parity.py --old-fixture-dir tests/fixtures/old_commerce --next-testclient --output-md /tmp/commerce_parity_gray.md --output-json /tmp/commerce_parity_gray.json
.venv/bin/python tools/compare_media_library_parity.py --old-fixture-dir tests/fixtures/old_media_library --next-testclient --output-md /tmp/media_parity_gray.md --output-json /tmp/media_parity_gray.json
```

## Batch Commands

| batch | required smoke | required parity | dual-run |
| --- | --- | --- | --- |
| Batch 1 Media Library readonly | `experiments/ai_crm_next/tools/media_library_gray_smoke.py --next-testclient` | Media parity | not required |
| Batch 2 Product Management readonly | `experiments/ai_crm_next/tools/product_management_gray_smoke.py --next-testclient` | Commerce parity | not required |
| Batch 3 Customer Read Model readonly | `experiments/ai_crm_next/tools/customer_read_model_gray_smoke.py --next-testclient` | Customer parity | old-base-url dual required before full gray |
| Batch 4 User Ops readonly | `experiments/ai_crm_next/tools/user_ops_readonly_gray_smoke.py --next-testclient` | User Ops parity | old-base-url dual required before full gray |
| Batch 5 Questionnaire readonly | `experiments/ai_crm_next/tools/questionnaire_readonly_gray_smoke.py --next-testclient` | Questionnaire parity | old-base-url dual recommended; accepted legacy drift allowed |
| Batch 6 Automation readonly | retired | retired | old automation_program/runtime-v2 parity and smoke tooling removed; `/admin/automation-conversion` is AI Audience |

## Frontend Screenshot Route Check

Confirm `experiments/ai_crm_next/docs/frontend_screenshot_baseline.md` includes the selected batch page routes and the latest route status remains `200`.

## Safety Checks

- no old write endpoint executed
- no real WeCom call
- no real OAuth call
- no real payment call
- no real OpenClaw call
- no real cloud storage upload
- no external webhook call
- rollback owner recorded
- rollback command reviewed
- signoff template completed

## Batch 1 Local Rehearsal

Before any production-like route flag change, run:

```bash
.venv/bin/python experiments/ai_crm_next/tools/run_gray_rehearsal_batch.py \
  --batch media_readonly \
  --next-testclient \
  --output-md /tmp/gray_rehearsal_batch_1_media_readonly.md \
  --output-json /tmp/gray_rehearsal_batch_1_media_readonly.json
```

Required result:

- `recommendation=GO`
- `production_config_modified=false`
- `old_write_endpoints_executed=false`
- `cloud_storage_upload_executed=false`
- `wecom_media_upload_executed=false`
- `real_traffic_cutover_executed=false`

## Batch 1 Staging Canary Readiness

Before a staging or production-like canary signoff, run:

```bash
.venv/bin/python experiments/ai_crm_next/tools/check_batch_1_media_canary_readiness.py \
  --media-smoke-json /tmp/media_gray_smoke_after_canary_plan.json \
  --media-parity-json /tmp/media_parity_after_canary_plan.json \
  --batch-rehearsal-json /tmp/gray_rehearsal_batch_1_media_readonly_audit.json \
  --output-md /tmp/batch_1_media_canary_readiness.md \
  --output-json /tmp/batch_1_media_canary_readiness.json
```

Required result:

- `readiness_status=canary_plan_ready`
- `recommendation=GO_TO_STAGING_CANARY_SIGNOFF`
- included routes are all GET
- excluded routes include Media Library POST/PUT/DELETE routes
- rollback dry-run is present
- screenshot baseline includes the three Media pages
- production config modified is false
- cloud storage and WeCom media remain disabled

## No-Go

Stop the batch if any condition is true:

- selected smoke has blockers
- parity has blockers
- Next route returns 5xx
- excluded route appears in smoke route results
- side-effect safety flag indicates real external call or old write
- rollback owner is missing
- fake adapter is represented as production validation
