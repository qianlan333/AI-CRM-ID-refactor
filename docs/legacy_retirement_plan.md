# Legacy Retirement Plan

AI-CRM default runtime has moved to AI-CRM Next. Legacy Flask remains as a fallback until production evidence allows deletion.

## Current State

- `python3 app.py run` starts AI-CRM Next.
- `python3 app.py run-legacy` starts legacy Flask.
- `wecom_ability_service/` and `openclaw_service/` are frozen, not deleted.
- Production traffic cutover is not executed by this plan.
- D1 Media Library old Flask route modules are retired/deleted. AI-CRM Next owns Media Library route handling by default.
- D2 Product Management old Flask admin route owner is retired/deleted. AI-CRM Next owns Product Management route handling by default; legacy checkout/payment files remain untouched fallback.
- D3 Customer Read Model old Flask readonly route owner is retired/deleted. AI-CRM Next owns customer list/detail/timeline route handling by default; legacy archive, contacts, identity, and mixed dependency packages remain fallback.
- D4 User Ops old Flask readonly route owner is retired/tombstoned. AI-CRM Next owns User Ops readonly page/list/overview/send-record routes by default; legacy User Ops write/external domain helpers remain fallback dependencies and are not delete-ready.
- D5 Questionnaire old Flask readonly route registrations are retired/tombstoned. AI-CRM Next owns questionnaire admin readonly, public readonly, and result readonly surfaces by default; legacy submit, OAuth, admin write, diagnostics, and external-push fallback code remains not delete-ready.
- D6 Automation old Flask readonly route registrations are retired/tombstoned. AI-CRM Next owns automation conversion overview/pools/members/execution-record readonly surfaces by default; legacy manual override, activation webhook, OpenClaw, workflow/runtime, agent, WeCom, and external fallback code remains not delete-ready.
- D6.5 Dead Legacy Cleanup is completed for safe no-reference readonly leftovers only. It deleted one orphaned D1 attachment-library template plus stale generated route-inventory artifacts. D7 write/external/runtime blockers remain protected and documented in `docs/d7_write_external_blocker_matrix.md`.
- D7 Write / External replacement planning is in progress. The executable planning package is `docs/d7_write_external_replacement_plan.md`, `docs/d7_adapter_contract_catalog.md`, and `docs/d7_capability_readiness_matrix.md`; D7.1 Media storage / WeCom media adapter contract is the recommended first implementation batch.

## Retirement Principles

- Delete only after production route evidence exists.
- Keep rollback possible until the relevant batch is signed off.
- Do not delete write or external adapter code until real replacement and rollback evidence exist.
- Do not mix multiple delete batches in one PR.

## Rollback Conditions

- Route smoke fails.
- Old fallback route is needed for recovery.
- External adapter behavior is not fully replaced.
- Data migration evidence is incomplete.

## Required Evidence Before Deletion

- Production canary or replacement evidence for the target route family.
- Latest smoke and parity report.
- Route owner proof.
- Rollback proof.
- Human signoff.

This document tracks the retirement plan and completed delete batches. It does not authorize deletion outside the explicitly completed batch list below.

## Completed Delete Batches

### D1: Media Library Old Routes

Deleted files:

- `wecom_ability_service/http/image_library_endpoint.py`
- `wecom_ability_service/http/image_library_create.py`
- `wecom_ability_service/http/attachment_library_endpoint.py`
- `wecom_ability_service/http/miniprogram_library_endpoint.py`

The legacy HTTP registrar no longer imports or registers these modules. Rollback is `git revert` of the D1 PR or restoring a pre-D1 fallback tag.

### D2: Product Management Old Routes

Deleted file:

- `wecom_ability_service/http/admin_wechat_pay_products.py`

The legacy HTTP registrar no longer imports or registers this module. AI-CRM Next `aicrm_next.commerce` owns Product Management admin/read surfaces by default.

Not deleted by D2:

- `wecom_ability_service/http/wechat_pay.py`
- `wecom_ability_service/http/alipay_pay.py`
- `wecom_ability_service/http/admin_wechat_pay.py`
- `wecom_ability_service/http/admin_alipay_pay.py`

Checkout, payment provider, return, notify, and transaction management remain legacy fallback and are not delete-ready. Product admin write fallback routes retire with the old Product Management owner, but Next product writes are still blocked until D7 evidence exists. Rollback is `git revert` of the D2 PR or restoring a pre-D2 fallback tag.

### D3: Customer Read Model Old Readonly Routes

Deleted files:

- `wecom_ability_service/http/customer_center.py`
- `wecom_ability_service/http/customer_timeline.py`

The legacy HTTP registrar no longer imports or registers these modules. AI-CRM Next `aicrm_next.customer_read_model` owns Customer Read Model list/detail/timeline routes by default. The legacy `/admin/customers` readonly page registration has been retired from `admin_customers.py`.

Retained mixed dependency packages:

- `wecom_ability_service/customer_center/`
- `wecom_ability_service/customer_timeline/`

They are retained with `LEGACY_DEPENDENCY_FALLBACK.md` because admin profile, automation, and MCP fallback paths still import their helpers.

Not deleted by D3:

- `wecom_ability_service/http/archive.py`
- `wecom_ability_service/http/contacts.py`
- `wecom_ability_service/http/identity.py`

`/api/messages/<external_userid>/recent` remains with legacy archive fallback until a later archive/external adapter retirement batch. Archive sync, WeCom conversation archive, tag refresh, OpenClaw, contacts, identity, and customer write capabilities remain not delete-ready. Rollback is `git revert` of the D3 PR or restoring a pre-D3 fallback tag. D4 User Ops old routes have not started.

### D4: User Ops Old Readonly Routes

Deleted or already-absent HTTP route owner files:

- `wecom_ability_service/http/admin_user_ops.py`
- `wecom_ability_service/http/admin_user_ops_delivery.py`

The legacy HTTP registrar has no `admin_user_ops` / `admin_user_ops_delivery` import or register entry. Legacy `/api/admin/user-ops*` and `/api/internal/user-ops*` requests remain blocked by the retired API guard before route dispatch. AI-CRM Next `aicrm_next.ops_enrollment` owns User Ops readonly surfaces by default.

Retained fallback dependencies:

- `wecom_ability_service/domains/user_ops/page_service.py`
- `wecom_ability_service/domains/user_ops/service.py`
- `wecom_ability_service/domains/user_ops/user_ops_deferred_job_service.py`
- `wecom_ability_service/domains/user_ops/hxc_send_config_service.py`
- `wecom_ability_service/http/admin_jobs.py`
- `wecom_ability_service/http/tasks.py`

DND, batch-send preview/execute, deferred jobs, WeCom dispatch, media upload, and internal job capabilities remain not delete-ready. D4 does not execute or approve those write/external paths. Rollback is `git revert` of the D4 PR or restoring a pre-D4 fallback tag.

### D5: Questionnaire Old Readonly Routes

Stopped legacy readonly route registrations:

- `GET /admin/questionnaires`
- `GET /admin/questionnaires/ui`
- `GET /admin/questionnaires/new`
- `GET /admin/questionnaires/<questionnaire_id>`
- `GET /api/admin/questionnaires`
- `GET /api/admin/questionnaires/preflight`
- `GET /api/admin/questionnaires/<questionnaire_id>`
- `GET /api/admin/questionnaires/<questionnaire_id>/latest-submit-debug`
- `GET /api/admin/questionnaires/<questionnaire_id>/export`
- `GET /s/<slug>`
- `GET /s/<slug>/submitted`
- `GET /s/<slug>/result/<result_token>`
- `GET /api/h5/questionnaires/<slug>`

D5 does not physically delete questionnaire mixed modules because they still carry submit, OAuth, admin write, diagnostics, and external-push fallback responsibilities.

Retained fallback files:

- `wecom_ability_service/http/admin_questionnaires.py`
- `wecom_ability_service/http/admin_questionnaire_console.py`
- `wecom_ability_service/http/public_questionnaires.py`
- `wecom_ability_service/http/public_questionnaire_oauth.py`
- `wecom_ability_service/http/public_questionnaire_diagnostics.py`
- `wecom_ability_service/http/admin_questionnaire_push_logs.py`
- `wecom_ability_service/http/questionnaire_support.py`
- `wecom_ability_service/domains/questionnaire/`

Questionnaire writes, public submit, OAuth, WeCom tag, webhook/external push, and external delivery capabilities remain not delete-ready. D5 does not execute or approve those write/external paths. Rollback is `git revert` of the D5 PR or restoring a pre-D5 fallback tag.

### D6: Automation Old Readonly Routes

Stopped legacy readonly route registrations:

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/<member_id>`
- `GET /api/admin/automation-conversion/execution-records`

Stopped legacy readonly alias/page registrations:

- `GET /admin/automation-conversion/programs/<program_id>/overview`
- `GET /admin/automation-conversion/programs/<program_id>/executions`
- `GET /admin/automation-conversion/programs/<program_id>/member-ops`
- `GET /api/admin/automation-conversion/dashboard`
- `GET /api/admin/automation-conversion/programs/<program_id>/members/segment-search`
- `GET /api/admin/automation-conversion/member`
- `GET /api/admin/automation-conversion/executions*`
- `GET /api/admin/automation-conversion/execution-items/<execution_item_id>`

D6 does not physically delete automation mixed modules because they still carry manual override, confirm conversion, OpenClaw push, activation webhook, workflow/runtime, agent, WeCom/external dispatch, and operation task fallback responsibilities.

Retained fallback files:

- `wecom_ability_service/http/automation_conversion.py`
- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/http/automation_conversion_member_api.py`
- `wecom_ability_service/http/automation_conversion_delivery.py`
- `wecom_ability_service/http/automation_conversion_runtime_api.py`
- `wecom_ability_service/http/automation_conversion_router_callback_api.py`
- `wecom_ability_service/http/automation_conversion_agent_api.py`
- `wecom_ability_service/http/automation_conversion_operation_tasks.py`
- `wecom_ability_service/http/automation_conversion_workflows.py`
- `wecom_ability_service/http/automation_conversion_review.py`
- `wecom_ability_service/domains/automation_conversion/`

Automation writes, activation webhook, OpenClaw push, workflow runtime, agent runtime, WeCom dispatch, and external webhook capabilities remain not delete-ready. D6 does not execute or approve those write/external/runtime paths. Rollback is `git revert` of the D6 PR or restoring a pre-D6 fallback tag. D7 write/external adapter retirement has not started.

### D6.5: Dead Legacy Cleanup

Deleted files:

- `wecom_ability_service/templates/admin_console/attachment_library.html`
- `docs/generated/route_inventory.md`
- `docs/generated/route_inventory.json`

D6.5 was limited to no-reference readonly leftovers and stale generated owner inventory. It did not delete write, external, runtime, payment, OAuth, WeCom, OpenClaw, archive, contacts, identity, or MCP fallback code. Full evidence is in `docs/legacy_dead_code_inventory.md`, `docs/legacy_d6_5_dead_cleanup_report.md`, and `tools/check_legacy_dead_cleanup.py`.

D7 write/external/runtime capabilities remain blocked and must go through replacement planning, tests, production evidence, rollback proof, and human approval before any further removal.

### D7: Write / External Replacement Planning

Status: planning in progress.

Planning artifacts:

- `docs/d7_write_external_replacement_plan.md`
- `docs/d7_adapter_contract_catalog.md`
- `docs/d7_capability_readiness_matrix.md`
- `tools/check_d7_replacement_planning.py`

Recommended first implementation batch: D7.1 Media storage and WeCom media adapter contract.

D8 old Flask shell retirement remains blocked. D9 OpenClaw legacy adapter retirement remains blocked. D7 planning does not authorize real external calls, production route changes, or legacy write/external/runtime deletion.
