# AI-CRM Next Fast Readonly Replacement Execution Plan

This plan is for fast, sequential, human-controlled readonly replacement. It does not execute production route changes by itself. Codex must not modify production config, set route flags, switch traffic, call external providers, or run write routes.

## Operating Principle

Move quickly by replacing one readonly batch at a time:

1. Human approves the batch window.
2. Ops applies the approved route change manually.
3. Codex or operator runs the batch smoke/parity command.
4. User performs the human test task list.
5. If pass, continue to the next batch.
6. If fail, rollback only that batch.

Do not combine batches in a single route change. The speed comes from short cycles, not from a single all-at-once cutover.

## Global Guardrails

- readonly routes only
- no old system write endpoint
- no Next write route with production effect
- no production PostgreSQL migration in this plan
- no real WeCom, OAuth, payment, OpenClaw, cloud storage, WeCom media, or external webhook unless a separate adapter approval exists
- no production approval wording is implied by this document
- rollback owner must be online before each batch starts

## Batch Sequence

| order | batch | module | expected human test time | proceed condition |
| --- | --- | --- | ---: | --- |
| 1 | `media_readonly` | Media Library | 10-15 min | pages and lists read normally; no upload/write |
| 2 | `product_readonly` | Product Management | 10-15 min | admin and public product reads are normal; checkout disabled |
| 3 | `customer_readonly` | Customer Read Model | 15-25 min | list/detail/timeline/recent messages read normally |
| 4 | `user_ops_readonly` | User Ops | 15-20 min | overview/list/filter/send records read normally |
| 5 | `questionnaire_readonly` | Questionnaire | 15-25 min | admin/public/result reads work; no submit/OAuth |
| 6 | `automation_readonly` | Automation Conversion | 15-25 min | overview/pools/members/execution records read normally |

## Batch 1: Media Library Readonly

Included:

- `GET /admin/image-library`
- `GET /api/admin/image-library`
- `GET /admin/attachment-library`
- `GET /api/admin/attachment-library`
- `GET /admin/miniprogram-library`
- `GET /api/admin/miniprogram-library`

Excluded:

- image/attachment/miniprogram create, update, delete, import, upload
- cloud storage upload
- WeCom media upload
- old system write routes

Validation:

```bash
.venv/bin/python tools/media_library_gray_smoke.py --next-testclient --output-md /tmp/media_fast_smoke.md --output-json /tmp/media_fast_smoke.json
.venv/bin/python tools/compare_media_library_parity.py --old-fixture-dir tests/fixtures/old_media_library --next-testclient --output-md /tmp/media_fast_parity.md --output-json /tmp/media_fast_parity.json
```

Rollback:

```bash
# Manual approved environment only
AICRM_NEXT_ROUTE_MEDIA_READONLY=false
```

## Batch 2: Product Management Readonly

Included:

- `GET /admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products/{product_id}`
- `GET /p/{page_slug}`
- `GET /api/products/{page_slug}`

Excluded:

- admin product create/update/enable/disable/delete
- checkout
- payment notify
- real WeChat Pay
- real Alipay

Validation:

```bash
.venv/bin/python tools/product_management_gray_smoke.py --next-testclient --output-md /tmp/product_fast_smoke.md --output-json /tmp/product_fast_smoke.json
.venv/bin/python tools/compare_commerce_parity.py --old-fixture-dir tests/fixtures/old_commerce --next-testclient --output-md /tmp/commerce_fast_parity.md --output-json /tmp/commerce_fast_parity.json
```

Rollback:

```bash
# Manual approved environment only
AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
```

## Batch 3: Customer Read Model Readonly

Included:

- `GET /admin/customers`
- `GET /api/customers`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/messages/{external_userid}/recent`

Excluded:

- customer write routes
- WeCom contact sync
- archive sync
- tag refresh
- OpenClaw push

Validation:

```bash
.venv/bin/python tools/customer_read_model_gray_smoke.py --next-testclient --output-md /tmp/customer_fast_smoke.md --output-json /tmp/customer_fast_smoke.json
.venv/bin/python tools/compare_customer_read_model_parity.py --old-fixture-dir tests/fixtures/old_customer_read_model --next-testclient --output-md /tmp/customer_fast_parity.md --output-json /tmp/customer_fast_parity.json
```

Rollback:

```bash
# Manual approved environment only
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
```

## Batch 4: User Ops Readonly

Included:

- `GET /admin/user-ops/ui`
- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/send-records`

Excluded:

- DND
- batch-send preview/execute
- deferred jobs
- internal user ops jobs
- WeCom dispatch
- WeCom media upload

Validation:

```bash
.venv/bin/python tools/user_ops_readonly_gray_smoke.py --next-testclient --output-md /tmp/user_ops_fast_smoke.md --output-json /tmp/user_ops_fast_smoke.json
.venv/bin/python tools/compare_user_ops_parity.py --old-fixture-dir tests/fixtures/old_user_ops --next-testclient --output-md /tmp/user_ops_fast_parity.md --output-json /tmp/user_ops_fast_parity.json
```

Rollback:

```bash
# Manual approved environment only
AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
```

## Batch 5: Questionnaire Readonly

Included:

- `GET /admin/questionnaires`
- `GET /admin/questionnaires/ui`
- `GET /api/admin/questionnaires`
- `GET /api/admin/questionnaires/{questionnaire_id}`
- `GET /api/admin/questionnaires/preflight`
- `GET /api/admin/questionnaires/{questionnaire_id}/latest-submit-debug`
- `GET /api/admin/questionnaires/{questionnaire_id}/export`
- `GET /s/{slug}`
- `GET /api/h5/questionnaires/{slug}`
- `GET /api/h5/questionnaires/{slug}/result/{submission_id}`

Excluded:

- admin create/update/delete/enable/disable
- H5 submit
- OAuth start/callback
- WeCom tag write
- external webhook/push

Validation:

```bash
.venv/bin/python tools/questionnaire_readonly_gray_smoke.py --next-testclient --output-md /tmp/questionnaire_fast_smoke.md --output-json /tmp/questionnaire_fast_smoke.json
.venv/bin/python tools/compare_questionnaire_parity.py --old-fixture-dir tests/fixtures/old_questionnaire --next-testclient --output-md /tmp/questionnaire_fast_parity.md --output-json /tmp/questionnaire_fast_parity.json
```

Rollback:

```bash
# Manual approved environment only
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
```

## Batch 6: Automation Conversion Readonly

Included:

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `GET /api/admin/automation-conversion/execution-records`

Excluded:

- manual override
- confirm conversion
- enter silent / exit marketing
- activation webhook
- OpenClaw push
- workflow runtime
- agent runtime
- WeCom dispatch
- external webhook

Validation:

```bash
.venv/bin/python tools/automation_readonly_gray_smoke.py --next-testclient --output-md /tmp/automation_fast_smoke.md --output-json /tmp/automation_fast_smoke.json
.venv/bin/python tools/compare_automation_conversion_parity.py --old-fixture-dir tests/fixtures/old_automation_conversion --next-testclient --output-md /tmp/automation_fast_parity.md --output-json /tmp/automation_fast_parity.json
```

Rollback:

```bash
# Manual approved environment only
AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false
```

## Stop Rules

Stop the current batch and rollback if any of these happen:

- any included route returns persistent 5xx
- smoke or parity has blocker
- write route receives traffic
- old system write endpoint is executed
- external adapter call appears unexpectedly
- route owner cannot be verified
- rollback owner is unavailable
- user reports page/data mismatch that blocks business use

## Operator Record

| field | value |
| --- | --- |
| active batch |  |
| operator |  |
| rollback owner |  |
| execution window |  |
| smoke result |  |
| parity result |  |
| user test result |  |
| continue / rollback |  |
| notes |  |
