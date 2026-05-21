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
- D7 Write / External adapter contracts are accepted through D7.7 in fake/staging-disabled form. Real external adapters remain disabled for production behavior.
- D8 Legacy Flask shell retirement is in phased readiness. D8.0 adds readiness planning, dependency inventory, allowed fallback matrix, checker, and tests only. D8.1 adds fallback route lockdown planning, retired readonly route matrix, checker, and tests only. D8.2 adds legacy-only runtime lockdown enforcement for retired D1-D6 readonly routes. D8.3 adds archive package move planning only. D8.4 creates the archive package entry layer. D8.5 plans legacy DB init and maintenance command retirement without deleting commands or executing production DB migration.
- D9 OpenClaw legacy adapter physical retirement planning is ready. D9.1 import freeze is ready. D9.2 move/archive planning is ready. D9.3 skeleton is created. D9.4 moved metadata into the archive package with a retained shim. D9.5 plans shim removal, D9.5.1 captures final reference-scan evidence, and D9.5.2 records the deletion-blocked state. D9.6 then physically removes the repo shim/archive after explicit owner approval and records server-side OpenClaw-named job removal with backup. Real OpenClaw/MCP behavior is not cut over.

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

`/api/messages/<external_userid>/recent` remains with legacy archive fallback until a later archive/external adapter retirement batch. Archive sync, WeCom conversation archive, tag refresh, OpenClaw, contacts, identity, and customer write capabilities remain not delete-ready. Rollback is `git revert` of the D3 PR or restoring a pre-D3 fallback tag. D4-D6 readonly retirement is completed below; D7 write/external/runtime deletion remains blocked.

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

Automation writes, activation webhook, OpenClaw push, workflow runtime, agent runtime, WeCom dispatch, and external webhook capabilities remain not delete-ready. D6 does not execute or approve those write/external/runtime paths. Rollback is `git revert` of the D6 PR or restoring a pre-D6 fallback tag. D7 write/external/runtime replacement planning is in progress and still does not authorize deletion.

### D6.5: Dead Legacy Cleanup

Deleted files:

- `wecom_ability_service/templates/admin_console/attachment_library.html`
- `docs/generated/route_inventory.md`
- `docs/generated/route_inventory.json`

D6.5 was limited to no-reference readonly leftovers and stale generated owner inventory. It did not delete write, external, runtime, payment, OAuth, WeCom, OpenClaw, archive, contacts, identity, or MCP fallback code. Full evidence is in `docs/legacy_dead_code_inventory.md`, `docs/legacy_d6_5_dead_cleanup_report.md`, and `tools/check_legacy_dead_cleanup.py`.

D7 write/external/runtime capabilities remain blocked and must go through replacement planning, tests, production evidence, rollback proof, and human approval before any further removal.

### D8.5: Legacy DB / Maintenance Command Planning

Status: `maintenance_command_retirement_planning_ready`.

D8.5 adds inventory, replacement matrix, readiness checker, and tests for legacy DB init and maintenance commands:

- `docs/d8_5_legacy_db_maintenance_command_inventory.md`
- `docs/d8_5_legacy_db_maintenance_command_retirement_plan.md`
- `docs/d8_5_maintenance_command_replacement_matrix.md`
- `tools/check_d8_5_legacy_maintenance_command_readiness.py`
- `tests/test_d8_5_legacy_maintenance_command_readiness.py`

Legacy DB init, cleanup, diagnostic, backfill, and rollback commands remain retained. Future command removal requires production migration evidence, backup/restore proof, runbook cleanup, rollback proof, and human signoff. D8.5 does not execute production DB migration, production cleanup, traffic cutover, external calls, or production config changes.

### D9.0: OpenClaw Legacy Adapter Physical Retirement Planning

Status: `openclaw_legacy_retirement_planning_ready`.

D9.0 adds the OpenClaw legacy adapter retirement plan, dependency inventory, compatibility matrix, checker, and tests:

- `docs/d9_openclaw_legacy_adapter_retirement_plan.md`
- `docs/d9_openclaw_legacy_dependency_inventory.md`
- `docs/d9_openclaw_mcp_compatibility_matrix.md`
- `tools/check_d9_openclaw_legacy_retirement_readiness.py`
- `tests/test_d9_openclaw_legacy_retirement_readiness.py`

`openclaw_service/` remains in place with `openclaw_service/LEGACY_FROZEN.md`. D9.0 does not move or remove the OpenClaw legacy adapter, does not call OpenClaw or external MCP services, does not send webhooks, does not cut production traffic, and does not modify production configuration. Future physical removal requires D7.7 real replacement evidence, no runtime imports, docs/scripts rewrite, plugin compatibility evidence, rollback proof, and human signoff.

### D9.1: OpenClaw Legacy Import Freeze

Status: `openclaw_import_freeze_ready`.

D9.1 adds the import freeze plan, allowlist, checker, and tests:

- `docs/d9_1_openclaw_legacy_import_freeze_plan.md`
- `docs/d9_1_openclaw_import_allowlist.md`
- `tools/check_d9_1_openclaw_import_freeze.py`
- `tests/test_d9_1_openclaw_import_freeze.py`

New runtime imports of `openclaw_service` are blocked. AI-CRM Next remains on the D7.7 MCP/OpenClaw adapter boundary. Static docs/tests/checker references remain allowed only as inventory and freeze assertions. D9.1 does not move or remove `openclaw_service/`, call OpenClaw, call external MCP services, send webhooks, cut traffic, or modify production configuration.

### D9.2: OpenClaw Legacy Move Planning

Status: `openclaw_legacy_move_planning_ready`.

D9.2 adds the move plan, move map, import rewrite plan, checker, and tests:

- `docs/d9_2_openclaw_legacy_move_plan.md`
- `docs/d9_2_openclaw_legacy_move_map.md`
- `docs/d9_2_openclaw_import_rewrite_plan.md`
- `tools/check_d9_2_openclaw_legacy_move_readiness.py`
- `tests/test_d9_2_openclaw_legacy_move_readiness.py`

D9.2 plans the future `openclaw_service/` to `legacy_flask/openclaw_legacy/` move. It does not create the runtime package, move files, remove the old path, call OpenClaw, call external MCP services, send webhooks, cut traffic, or modify production configuration. D9.3 may start package skeleton or move implementation only after D9.2 acceptance.

### D9.3: OpenClaw Legacy Archive Skeleton

Status: `openclaw_legacy_skeleton_created`.

D9.3 creates the skeleton archive package and skeleton readiness checker:

- `legacy_flask/openclaw_legacy/__init__.py`
- `legacy_flask/openclaw_legacy/README.md`
- `legacy_flask/openclaw_legacy/LEGACY_FROZEN.md`
- `legacy_flask/openclaw_legacy/MOVE_PENDING.md`
- `docs/d9_3_openclaw_legacy_skeleton_implementation_report.md`
- `tools/check_d9_3_openclaw_legacy_skeleton.py`
- `tests/test_d9_3_openclaw_legacy_skeleton.py`

The skeleton does not import `openclaw_service` and does not expose a runtime adapter. `openclaw_service/` and `openclaw_service/LEGACY_FROZEN.md` remain in place during D9.3. D9.4 is the move-with-shim phase.

### D9.4: OpenClaw Legacy Move With Shim

Status: `openclaw_legacy_files_moved_with_shim`.

D9.4 keeps `openclaw_service/` as a compatibility shim and records the frozen legacy marker under `legacy_flask/openclaw_legacy/`. The shim is metadata-only, keeps old imports from crashing, and does not expose an OpenClaw runtime adapter.

AI-CRM Next continues through the D7.7 MCP/OpenClaw adapter boundary. D9.4 does not modify production configuration, cut traffic, call OpenClaw, call external MCP services, or send webhooks.

### D9.5: OpenClaw Shim Removal Planning

Status: `openclaw_shim_removal_planning_ready`.

D9.5 adds the shim-removal plan, final reference scan plan, readiness checklist, checker, and tests. It keeps `openclaw_service/`, `openclaw_service/__init__.py`, `openclaw_service/README.md`, `openclaw_service/LEGACY_FROZEN.md`, and `legacy_flask/openclaw_legacy/` in place.

D9.5 does not remove the shim, modify production configuration, cut traffic, call OpenClaw, call external MCP services, or send webhooks. D9.5.1 is the next evidence-capture step.

### D7: Write / External Adapter Contracts

Status: accepted through D7.7 in fake/staging-disabled form.

Planning artifacts:

- `docs/d7_write_external_replacement_plan.md`
- `docs/d7_adapter_contract_catalog.md`
- `docs/d7_capability_readiness_matrix.md`
- `tools/check_d7_replacement_planning.py`

Completed fake/staging-disabled contract gates:

- D7.1 Media storage / WeCom media adapter.
- D7.2 Questionnaire submit / OAuth / WeCom tag / external push adapter.
- D7.3 User Ops DND / batch-send / WeCom dispatch / deferred-job adapter.
- D7.4 Product writes / WeChat Pay / Alipay / notify / return adapter.
- D7.5 Automation write / OpenClaw / workflow runtime / agent runtime adapter.
- D7.6 Archive sync / contacts sync / identity mapping / customer projection adapter.
- D7.7 MCP / OpenClaw legacy adapter.

Real cloud upload, real WeCom media upload, real OAuth, real payment provider calls, real MCP external calls, real OpenClaw calls, real archive/contact sync, production route changes, and legacy write/external/runtime deletion remain blocked until later evidence and signoff.

### D8: Legacy Flask Shell Retirement Planning

Status: D8.4 archive package created.

Artifacts:

- `docs/d8_legacy_flask_shell_retirement_plan.md`
- `docs/d8_legacy_shell_dependency_inventory.md`
- `docs/d8_legacy_shell_allowed_fallback_matrix.md`
- `tools/check_d8_legacy_shell_retirement_readiness.py`
- `docs/d8_1_legacy_fallback_route_lockdown_plan.md`
- `docs/d8_1_legacy_fallback_route_matrix.md`
- `tools/check_d8_1_legacy_fallback_route_lockdown.py`
- `docs/d8_2_legacy_fallback_route_lockdown_enforcement.md`
- `docs/d8_2_legacy_fallback_route_lockdown_report.md`
- `tools/check_d8_2_legacy_lockdown_enforcement.py`
- `docs/d8_3_legacy_flask_shell_archive_package_plan.md`
- `docs/d8_3_legacy_package_move_map.md`
- `docs/d8_3_legacy_import_rewrite_plan.md`
- `tools/check_d8_3_legacy_archive_move_readiness.py`
- `legacy_flask/app_factory.py`
- `legacy_flask/routes.py`
- `legacy_flask/http/__init__.py`
- `legacy_flask/legacy_lockdown.py`
- `tools/check_d8_4_legacy_archive_package.py`

D8.1 status is `lockdown_planning_ready`. D8.2 status is `lockdown_enforcement_implemented`. D8.3 status is `archive_move_planning_ready`. D8.4 status is `archive_package_created`. D8.4 creates `legacy_flask/` for the entry layer and keeps `wecom_ability_service/` as a compatibility shim and legacy module holder. It does not move `openclaw_service/`, delete `legacy_flask_app.py`, modify production config, cut traffic, run old writes, or enable real external adapters.
