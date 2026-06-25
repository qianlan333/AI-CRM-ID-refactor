# Route-Level Gray Release Batches

This plan is a controlled execution design only. It does not switch production traffic, modify production Nginx, connect production PostgreSQL, or enable real WeCom, OAuth, payment, OpenClaw, webhook, or cloud adapters.

## Batch 0: Evidence-Only Validation

Included routes:

- none

Excluded routes:

- all production route cutover
- all write routes
- all external provider routes

Entry criteria:

- Ordinary pytest passes.
- Six parity reports pass.
- Real local PostgreSQL integration evidence is available.
- Frontend screenshot baseline is available.
- Readonly dual-run reports are archived.

Smoke commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tools/capture_frontend_screenshots.py --output-dir artifacts/frontend_screenshots --mode testclient
.venv/bin/python tools/readonly_http_dual_run.py --old-base-url http://127.0.0.1:5001 --next-testclient --scope customer,user_ops --output-md /tmp/aicrm_next_readonly_dual_run.md --output-json /tmp/aicrm_next_readonly_dual_run.json
```

Monitoring signals:

- pytest/parity status
- screenshot route status
- readonly dual-run blockers, warnings, and skipped
- architecture boundary scan

Rollback trigger:

- any blocker in evidence reports
- old-service write endpoint detected
- real external adapter accidentally enabled

Rollback command placeholder:

```bash
# PSEUDO ONLY - no production traffic is switched in Batch 0.
```

Signoff required:

- release owner
- module owner for any failed evidence

## Batch 1: Media Library Readonly

Included routes:

- `GET /admin/image-library`
- `GET /api/admin/image-library`
- `GET /admin/attachment-library`
- `GET /api/admin/attachment-library`
- `GET /admin/miniprogram-library`
- `GET /api/admin/miniprogram-library`

Excluded routes:

- `POST /api/admin/image-library`
- `POST /api/admin/image-library/from-url`
- `POST /api/admin/image-library/from-base64`
- `PUT /api/admin/image-library/{image_id}`
- `DELETE /api/admin/image-library/{image_id}`
- attachment/miniprogram create, update, delete routes
- cloud storage upload
- WeCom media upload

Entry criteria:

- Batch 0 passes.
- Media parity passes.
- Media default gray smoke passes.
- Route cutover manifest and rollback owner are confirmed.

Smoke commands:

```bash
.venv/bin/python tools/media_library_gray_smoke.py --next-testclient --output-md /tmp/media_library_gray_smoke.md --output-json /tmp/media_library_gray_smoke.json
.venv/bin/python tools/compare_media_library_parity.py --old-fixture-dir tests/fixtures/old_media_library --next-testclient --output-md /tmp/media_parity.md --output-json /tmp/media_parity.json
```

Monitoring signals:

- read route status
- media list envelope shape
- side-effect safety flags
- storage adapter mode remains fake

Rollback trigger:

- read route returns 5xx
- missing required list keys
- cloud or WeCom upload appears in logs

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_MEDIA_READONLY=false
# Restore route owner to old Flask in the approved proxy/app route layer.
```

Signoff required:

- media owner
- release owner

Latest local rehearsal:

- `docs/gray_rehearsal_batch_1_media_readonly.md`
- `docs/gray_rehearsal_batch_1_route_flags.md`
- `/tmp/gray_rehearsal_batch_1_media_readonly.json`
- status: PASS / local dry-run only
- production config modified: false
- real traffic cutover executed: false
- cloud storage upload executed: false
- WeCom media upload executed: false

Staging canary plan:

- `docs/staging_canary_topology.md`
- `docs/batch_1_media_readonly_canary_plan.md`
- `docs/batch_1_media_readonly_canary_runbook.md`
- `docs/batch_1_media_readonly_proxy_pseudo_config.md`
- `tools/check_batch_1_media_canary_readiness.py`
- status: canary_plan_ready after the readiness checker passes
- production traffic not cut
- real cloud storage and WeCom media remain disabled

Latest staging-simulated canary execution:

- `docs/batch_1_media_readonly_canary_execution_report.md`
- `docs/batch_1_media_readonly_canary_signoff.md`
- `/tmp/media_gray_smoke_staging_simulated_canary.json`
- `/tmp/media_parity_after_canary_execute.json`
- `/tmp/gray_release_media_readonly_staging_simulated_canary_report.json`
- status: PASS / staging simulated only
- production config modified: false
- real traffic cutover executed: false
- cloud storage upload executed: false
- WeCom media upload executed: false

## Batch 2: Product Management Readonly

Included routes:

- `GET /admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products/{product_id}`
- `GET /p/{page_slug}`
- `GET /api/products/{page_slug}`

Excluded routes:

- checkout
- payment notify
- `POST /api/checkout/wechat`
- `POST /api/checkout/alipay`
- admin product create, update, enable, disable, delete
- real WeChat Pay
- real Alipay

Entry criteria:

- Batch 0 passes.
- Commerce parity passes.
- Product default gray smoke passes.
- Checkout/payment provider mode is confirmed fake/disabled.

Smoke commands:

```bash
.venv/bin/python tools/product_management_gray_smoke.py --next-testclient --output-md /tmp/product_management_gray_smoke.md --output-json /tmp/product_management_gray_smoke.json
.venv/bin/python tools/compare_commerce_parity.py --old-fixture-dir tests/fixtures/old_commerce --next-testclient --output-md /tmp/commerce_parity.md --output-json /tmp/commerce_parity.json
```

Monitoring signals:

- product page 200
- product API read shape
- checkout/payment safety flags

Rollback trigger:

- product read route returns 5xx
- payment/checkout path appears in smoke
- provider call appears in logs

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
# Restore product read routes to old Flask.
```

Signoff required:

- commerce owner
- release owner

Latest staging-simulated canary execution:

- `docs/batch_2_product_readonly_canary_execution_report.md`
- `docs/batch_2_product_readonly_canary_signoff.md`
- `/tmp/product_management_gray_smoke_batch_2.json`
- `/tmp/commerce_parity_batch_2_product.json`
- `/tmp/batch_2_product_canary_readiness.json`
- mode: `staging_simulated_canary`
- readiness: `canary_plan_ready`
- recommendation: `GO_TO_STAGING_CANARY_SIGNOFF`
- production config modified: false
- real traffic cutover executed: false
- checkout executed: false
- payment provider called: false
- external payment executed: false
- signoff status: `staging_simulated_only`

## Batch 3: Customer Read Model Readonly

Included routes:

- `GET /admin/customers`
- `GET /api/customers`
- `GET /api/customers?limit=5&offset=0`
- `GET /api/customers?owner_userid={owner_userid}`
- `GET /api/customers?is_bound=true`
- `GET /api/customers?keyword={keyword}`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/customers/{external_userid}/timeline?limit=5&offset=0`
- `GET /api/messages/{external_userid}/recent`
- `GET /api/messages/{external_userid}/recent?limit=5`

Excluded routes:

- any customer write route
- WeCom contact sync
- message archive sync
- tag refresh
- OpenClaw webhook

Entry criteria:

- Batch 0 passes.
- Customer parity passes.
- Customer gray smoke passes.
- Masked sample external_userid evidence exists for detail/timeline/recent messages.

Smoke commands:

```bash
.venv/bin/python tools/customer_read_model_gray_smoke.py --next-testclient --output-md /tmp/customer_read_model_gray_smoke.md --output-json /tmp/customer_read_model_gray_smoke.json
.venv/bin/python tools/customer_read_model_gray_smoke.py --old-base-url http://127.0.0.1:5001 --next-testclient --output-md /tmp/customer_read_model_gray_smoke_dual.md --output-json /tmp/customer_read_model_gray_smoke_dual.json
```

Monitoring signals:

- customer list/detail/timeline/recent status
- sample availability
- side-effect safety flags

Rollback trigger:

- Next read route 5xx
- missing required OpenClaw read contract keys
- WeCom/archive/tag refresh detected

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
# Restore customer read routes to old Flask.
```

Signoff required:

- customer read owner
- release owner

Latest staging-simulated canary execution:

- `docs/batch_3_customer_readonly_canary_execution_report.md`
- `docs/batch_3_customer_readonly_canary_signoff.md`
- `/tmp/customer_gray_smoke_batch_3.json`
- `/tmp/customer_parity_batch_3.json`
- `/tmp/readonly_dual_run_batch_3_customer.json`
- `/tmp/batch_3_customer_canary_readiness.json`
- mode: `staging_simulated_canary`
- sample external_userid: `external_user_masked_001`
- readiness: `canary_plan_ready`
- recommendation: `GO_TO_STAGING_CANARY_SIGNOFF`
- production config modified: false
- real traffic cutover executed: false
- old write endpoints executed: false
- WeCom sync/archive sync/tag refresh/OpenClaw executed: false
- signoff status: `staging_simulated_only`

## Batch 4: User Ops Readonly

Included routes:

- `GET /admin/user-ops/ui`
- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/list?wecom_status=added`
- `GET /api/admin/user-ops/list?wecom_status=not_added`
- `GET /api/admin/user-ops/list?mobile_binding_status=bound`
- `GET /api/admin/user-ops/list?activation_bucket=activated`
- `GET /api/admin/user-ops/send-records`
- `GET /api/admin/user-ops/send-records/{record_id}` only when a stable sample is available

Excluded routes:

- DND
- batch-send preview
- batch-send execute
- deferred jobs
- internal user-ops writes
- real WeCom dispatch
- real media upload

Entry criteria:

- Batch 0 passes.
- User Ops parity passes.
- User Ops readonly gray smoke passes.
- User Ops readonly dual-run passes with only accepted legacy drift.
- Accepted legacy drift for old missing `激活待录入` is recorded.
- Next overview still includes `激活待录入`.

Smoke commands:

```bash
.venv/bin/python tools/user_ops_readonly_gray_smoke.py --next-testclient --output-md /tmp/user_ops_readonly_gray_smoke.md --output-json /tmp/user_ops_readonly_gray_smoke.json
.venv/bin/python tools/user_ops_readonly_gray_smoke.py --old-base-url http://127.0.0.1:5001 --next-testclient --output-md /tmp/user_ops_readonly_gray_smoke_dual.md --output-json /tmp/user_ops_readonly_gray_smoke_dual.json
.venv/bin/python tools/check_batch_4_user_ops_canary_readiness.py --user-ops-smoke-json /tmp/user_ops_readonly_gray_smoke_batch_4.json --user-ops-parity-json /tmp/user_ops_parity_batch_4.json --readonly-dual-json /tmp/readonly_dual_run_batch_4_user_ops.json --output-md /tmp/batch_4_user_ops_canary_readiness.md --output-json /tmp/batch_4_user_ops_canary_readiness.json
```

Monitoring signals:

- overview 8-card contract
- list filter shape
- send records envelope
- WeCom dispatch flags

Rollback trigger:

- Next route 5xx
- Next missing `激活待录入`
- DND/batch-send/deferred job appears in smoke or logs

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
# Restore User Ops read routes to old Flask.
```

Signoff required:

- User Ops owner
- release owner

Current Batch 4 simulated evidence:

- docs:
  - `docs/batch_4_user_ops_readonly_canary_plan.md`
  - `docs/batch_4_user_ops_readonly_route_flags.md`
  - `docs/batch_4_user_ops_readonly_canary_runbook.md`
  - `docs/batch_4_user_ops_readonly_proxy_pseudo_config.md`
  - `docs/batch_4_user_ops_readonly_canary_execution_report.md`
  - `docs/batch_4_user_ops_readonly_canary_signoff.md`
- readiness checker: `tools/check_batch_4_user_ops_canary_readiness.py`
- mode: `staging_simulated_canary`
- readiness: `canary_plan_ready`
- production config modified: false
- real traffic cutover executed: false
- DND/batch-send/deferred jobs executed: false
- WeCom dispatch/media upload executed: false
- signoff status: `staging_simulated_only`

## Batch 5: Questionnaire Readonly

Included routes:

- `GET /admin/questionnaires`
- `GET /admin/questionnaires/ui`
- `GET /api/admin/questionnaires`
- `GET /api/admin/questionnaires/{id}`
- `GET /api/admin/questionnaires/preflight`
- `GET /api/admin/questionnaires/{id}/latest-submit-debug`
- `GET /api/admin/questionnaires/{id}/export`
- `GET /s/{slug}`
- `GET /api/h5/questionnaires/{slug}`
- `GET /api/h5/questionnaires/{slug}/result/{submission_id}`
- `GET /s/{slug}/result/{result_token}` only as legacy result page evidence when needed

Excluded routes:

- submit
- OAuth callback
- OAuth start for real provider
- external push
- admin create/update/delete/enable/disable
- WeCom tag mutation
- webhook retry

Entry criteria:

- Batch 0 passes.
- Questionnaire parity passes.
- Questionnaire readonly gray smoke passes.
- Accepted legacy public API/result differences are recorded.
- Batch 5 readiness checker passes.

Smoke commands:

```bash
.venv/bin/python tools/questionnaire_readonly_gray_smoke.py --next-testclient --output-md /tmp/questionnaire_readonly_gray_smoke.md --output-json /tmp/questionnaire_readonly_gray_smoke.json
.venv/bin/python tools/questionnaire_readonly_gray_smoke.py --old-base-url http://127.0.0.1:5001 --next-testclient --output-md /tmp/questionnaire_readonly_gray_smoke_dual.md --output-json /tmp/questionnaire_readonly_gray_smoke_dual.json
.venv/bin/python tools/check_batch_5_questionnaire_canary_readiness.py --questionnaire-smoke-json /tmp/questionnaire_readonly_gray_smoke_batch_5.json --questionnaire-parity-json /tmp/questionnaire_parity_batch_5.json --output-md /tmp/batch_5_questionnaire_canary_readiness.md --output-json /tmp/batch_5_questionnaire_canary_readiness.json
```

Monitoring signals:

- admin/public read status
- fake OAuth remains fake
- submit remains disabled by default
- webhook side-effect flags

Rollback trigger:

- Next read route 5xx
- submit/OAuth callback/admin write appears in smoke
- real OAuth/WeCom/webhook detected

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
# Restore questionnaire read routes to old Flask.
```

Signoff required:

- questionnaire owner
- release owner

Current Batch 5 simulated evidence:

- docs:
  - `docs/batch_5_questionnaire_readonly_canary_plan.md`
  - `docs/batch_5_questionnaire_readonly_route_flags.md`
  - `docs/batch_5_questionnaire_readonly_canary_runbook.md`
  - `docs/batch_5_questionnaire_readonly_proxy_pseudo_config.md`
  - `docs/batch_5_questionnaire_readonly_canary_execution_report.md`
  - `docs/batch_5_questionnaire_readonly_canary_signoff.md`
- readiness checker: `tools/check_batch_5_questionnaire_canary_readiness.py`
- mode: `staging_simulated_canary`
- readiness: `canary_plan_ready`
- production config modified: false
- real traffic cutover executed: false
- submit/OAuth/WeCom tag/external webhook executed: false
- signoff status: `staging_simulated_only`

## Batch 6: Automation Readonly

Included routes:

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `GET /api/admin/automation-conversion/execution-records`

Excluded routes:

- manual override
- confirm conversion
- enter silent
- exit marketing
- activation webhook
- OpenClaw push
- workflow runtime
- agent runtime
- real WeCom dispatch
- external webhook
- old system writes
- production route cutover

Entry criteria:

- Retired. The old Automation Conversion readonly/parity path is no longer a
  controlled execution batch because automation_program/runtime-v2 has been
  replaced by AI Audience.

Smoke commands:

```bash
# No command. Batch 6 old Automation readonly tooling was retired.
```

Monitoring signals:

- overview/pools/members read status
- old route alias status
- OpenClaw/WeCom/webhook/runtime safety flags

Rollback trigger:

- Next route 5xx
- required Next shape key missing
- activation webhook/OpenClaw/WeCom/webhook/runtime detected

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false
# Restore Automation read routes to old Flask.
```

Signoff required:

- automation owner
- release owner
