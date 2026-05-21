# Legacy Delete Batches

Deletion is intentionally separated from the runtime switch.

## D0: Freeze Only

- Mark `wecom_ability_service/` as legacy fallback.
- Mark `openclaw_service/` as legacy adapter/reference.
- Switch `app.py run` to AI-CRM Next.
- Keep `run-legacy` and `legacy_flask_app.py`.

## D1: Media Old Readonly Routes

Status: retired/deleted.

Deleted legacy HTTP route modules:

- `wecom_ability_service/http/image_library_endpoint.py`
- `wecom_ability_service/http/image_library_create.py`
- `wecom_ability_service/http/attachment_library_endpoint.py`
- `wecom_ability_service/http/miniprogram_library_endpoint.py`

Legacy HTTP registrar entries for these modules have been removed. Fallback owner is AI-CRM Next via `aicrm_next.media_library` and `frontend_compat` pages.

Rollback:

- Revert the D1 PR, or
- Restore the legacy fallback service from a pre-D1 tag/commit.

## D2: Product Old Readonly Routes

Status: retired/deleted.

Deleted legacy HTTP route module:

- `wecom_ability_service/http/admin_wechat_pay_products.py`

Legacy HTTP registrar entries for this module have been removed. Fallback owner is AI-CRM Next via `aicrm_next.commerce` and `frontend_compat` pages.

Untouched payment / checkout files:

- `wecom_ability_service/http/wechat_pay.py`
- `wecom_ability_service/http/alipay_pay.py`
- `wecom_ability_service/http/admin_wechat_pay.py`
- `wecom_ability_service/http/admin_alipay_pay.py`

Checkout, payment return, and payment notify routes remain legacy fallback and are not delete-ready. Product admin write fallback routes went down with the Product Management owner, but Next product writes remain blocked until D7 evidence exists.

Rollback:

- Revert the D2 PR, or
- Restore the legacy fallback service from a pre-D2 tag/commit.

## D3: Customer Old Readonly Routes

Status: retired/deleted.

Deleted legacy HTTP route modules:

- `wecom_ability_service/http/customer_center.py`
- `wecom_ability_service/http/customer_timeline.py`

Legacy HTTP registrar entries for these modules have been removed. The legacy `/admin/customers` readonly page registration has also been retired from `admin_customers.py`; customer profile APIs and customer write fallbacks remain importable but are not part of D3 readonly ownership.

Retained mixed-dependency fallback packages:

- `wecom_ability_service/customer_center/`
- `wecom_ability_service/customer_timeline/`

These packages are retained because admin profile, automation context, and MCP fallback code still import their helpers. They are marked `LEGACY_DEPENDENCY_FALLBACK.md` and must not receive new business features.

Untouched archive / contacts / identity files:

- `wecom_ability_service/http/archive.py`
- `wecom_ability_service/http/contacts.py`
- `wecom_ability_service/http/identity.py`

The legacy `/api/messages/<external_userid>/recent` route remains with `archive.py` as archive fallback and is not counted as a D3 blocker. Archive sync, WeCom conversation archive, contact identity, tag refresh, and external sync/write capabilities remain not delete-ready.

Rollback:

- Revert the D3 PR, or
- Restore the legacy fallback service from a pre-D3 tag/commit.

## D4: User Ops Old Readonly Routes

Status: retired/tombstoned.

Deleted or already-absent legacy HTTP route owner modules:

- `wecom_ability_service/http/admin_user_ops.py`
- `wecom_ability_service/http/admin_user_ops_delivery.py`

The legacy HTTP registrar has no `admin_user_ops` / `admin_user_ops_delivery` import or register entry. Legacy `/api/admin/user-ops*` and `/api/internal/user-ops*` requests are blocked before route dispatch with the existing retired API guard. AI-CRM Next owns the User Ops readonly page and API surfaces via `aicrm_next.ops_enrollment` and `frontend_compat`.

Retained User Ops write / external fallback dependencies:

- `wecom_ability_service/domains/user_ops/page_service.py`
- `wecom_ability_service/domains/user_ops/service.py`
- `wecom_ability_service/domains/user_ops/user_ops_deferred_job_service.py`
- `wecom_ability_service/domains/user_ops/hxc_send_config_service.py`
- `wecom_ability_service/http/admin_jobs.py`
- `wecom_ability_service/http/tasks.py`

DND, batch-send, deferred jobs, WeCom dispatch, and media upload capabilities remain not delete-ready. D4 does not execute or approve those write/external paths. If a legacy admin User Ops route owner is needed for rollback, restore it by reverting the D4/D0-D4 retirement PR chain or by using a pre-D4 fallback tag.

D7.3 now provides fake User Ops adapter contracts for DND, batch-send, WeCom dispatch, and deferred jobs under `aicrm_next/integration_gateway/user_ops_adapters.py`. The retained legacy fallback dependencies above still stay in place because real external calls, worker execution, production evidence, rollback proof, and human approval are not present.

## D5: Questionnaire Old Readonly Routes

Status: retired/tombstoned.

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

No questionnaire files were physically deleted in D5 because the legacy modules are read/write mixed. `admin_questionnaires.py`, `admin_questionnaire_console.py`, and `public_questionnaires.py` remain registered only for write/submit fallback paths. AI-CRM Next owns the Questionnaire readonly page/API/result surfaces via `aicrm_next.questionnaire` and `frontend_compat`.

Retained Questionnaire write / external fallback files:

- `wecom_ability_service/http/admin_questionnaires.py`
- `wecom_ability_service/http/admin_questionnaire_console.py`
- `wecom_ability_service/http/public_questionnaires.py`
- `wecom_ability_service/http/public_questionnaire_oauth.py`
- `wecom_ability_service/http/public_questionnaire_diagnostics.py`
- `wecom_ability_service/http/admin_questionnaire_push_logs.py`
- `wecom_ability_service/http/questionnaire_support.py`
- `wecom_ability_service/domains/questionnaire/`

Admin writes, public submit, OAuth start/callback, client diagnostics, external push log list/retry, WeCom tag writes, and webhook/external delivery paths remain not delete-ready. D5 does not execute or approve submit, OAuth, WeCom tag, or webhook paths. If a legacy questionnaire readonly route owner is needed for rollback, restore it by reverting the D5 PR or by using a pre-D5 fallback tag.

## D6: Automation Old Readonly Routes

Status: retired/tombstoned.

Stopped legacy readonly route registrations:

- `GET /admin/automation-conversion`
- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `GET /api/admin/automation-conversion/execution-records`

Stopped legacy readonly alias/page registrations:

- `GET /admin/automation-conversion/programs/{program_id}/overview`
- `GET /admin/automation-conversion/programs/{program_id}/executions`
- `GET /admin/automation-conversion/programs/{program_id}/member-ops`
- `GET /api/admin/automation-conversion/dashboard`
- `GET /api/admin/automation-conversion/programs/{program_id}/members/segment-search`
- `GET /api/admin/automation-conversion/member`
- `GET /api/admin/automation-conversion/executions`
- `GET /api/admin/automation-conversion/executions/{execution_id}`
- `GET /api/admin/automation-conversion/executions/{execution_id}/items`
- `GET /api/admin/automation-conversion/execution-items/{execution_item_id}`

No automation files were physically deleted in D6 because `automation_conversion.py` is a mixed registrar for readonly, write, external, workflow/runtime, agent, and OpenClaw fallback paths. AI-CRM Next owns the Automation readonly page/API surfaces via `aicrm_next.automation_engine` and `frontend_compat`.

Retained Automation write / external / runtime fallback files:

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

Manual override, confirm conversion, enter/exit, activation webhook, OpenClaw push, workflow runtime, agent runtime, router callbacks, WeCom dispatch, and external webhook capabilities remain not delete-ready. D6 does not execute or approve those write/external/runtime paths. If a legacy automation readonly route owner is needed for rollback, restore it by reverting the D6 PR or by using a pre-D6 fallback tag.

## D6.5: Dead Legacy Cleanup

Status: completed for no-reference readonly leftovers only.

Physically deleted in D6.5:

- `wecom_ability_service/templates/admin_console/attachment_library.html`
- `docs/generated/route_inventory.md`
- `docs/generated/route_inventory.json`

The deleted template belonged to the retired D1 attachment-library old route owner. AI-CRM Next serves `/admin/attachment-library` through `frontend_compat` and does not render this template. The generated route inventory files were unreferenced stale legacy owner artifacts after D1-D6 retirement.

Not deleted by D6.5:

- any payment checkout / notify / return file
- any Questionnaire submit / OAuth / admin write / external-push file
- any User Ops DND / batch-send / deferred job file
- any Automation manual override / activation / OpenClaw / workflow / agent runtime file
- archive, contacts, identity, MCP, OpenClaw, deploy, schema, or migration files

D7 remains blocked by `docs/d7_write_external_blocker_matrix.md`.

## D7: Write And External Adapters

Status: replacement planning in progress; D7.1 fake media adapter contract implemented; D7.2 fake Questionnaire submit/OAuth/WeCom tag/external push adapter contract implemented; D7.3 fake User Ops DND/batch-send/WeCom dispatch/deferred-job adapter contract implemented; D7.4 fake Product/Payment adapter contract implemented; D7.5 fake Automation write/OpenClaw/workflow/agent adapter contract implemented; D7.6 fake Archive/Contacts/Identity/Customer Projection adapter contract implemented; D7.7 fake MCP/OpenClaw legacy adapter contract implemented. Delete only after real write/external/runtime/sync replacement evidence and explicit provider approval.

Planning package:

- `docs/d7_write_external_replacement_plan.md`
- `docs/d7_adapter_contract_catalog.md`
- `docs/d7_capability_readiness_matrix.md`
- `tools/check_d7_replacement_planning.py`

D7.6 package:

- `aicrm_next/integration_gateway/customer_sync_contracts.py`
- `aicrm_next/integration_gateway/customer_sync_adapters.py`
- `docs/d7_6_archive_contacts_identity_adapter_contract.md`
- `docs/d7_6_archive_contacts_identity_adapter_implementation_report.md`
- `tools/check_d7_6_customer_sync_adapter_contract.py`

Archive, contacts, identity, and customer projection legacy fallback remain retained because real WeCom archive sync, real contacts sync, identity writes, production projection writes, production evidence, rollback proof, and human approval are not present.

D7.4 provides fake Product write, WeChat Pay, Alipay, notify, and return adapter contracts under `aicrm_next/integration_gateway/payment_adapters.py`. The retained legacy payment fallback files still stay in place because real provider calls, production notify handling, payment reconciliation, rollback proof, and human approval are not present.

D7.1 Media storage and WeCom media adapter contract now provides fake/staging-disabled CloudStorageAdapter and WeComMediaAdapter boundaries. Real cloud upload and real WeCom media upload remain blocked. D8 and D9 remain blocked.

D7.2 Questionnaire submit/OAuth/WeCom tag/external push adapter contract now provides fake/staging-disabled WeChatOAuthAdapter, WeComTagAdapter, QuestionnaireExternalPushAdapter, and QuestionnaireSubmitSideEffectGateway boundaries. Real OAuth, real WeCom tag writes, and real webhook delivery remain blocked. Legacy questionnaire submit/OAuth/external fallback is retained and is not ready for deletion.

D7.5 Automation write/OpenClaw/workflow/agent adapter contract now provides fake/staging-disabled AutomationWriteGateway, AutomationActivationGateway, OpenClawWebhookAdapter, AutomationWorkflowRuntimeAdapter, and AutomationAgentRuntimeAdapter boundaries. Real Automation writes, activation webhook side effects, OpenClaw push, workflow runtime, and agent runtime remain blocked. Legacy automation write/external/runtime fallback is retained and is not ready for deletion.

## D8: Old Flask App Factory And HTTP Registrar

Status: not started. Delete only after all legacy routes are retired and rollback no longer depends on Flask.

## D9: OpenClaw Legacy Adapter Retirement

Status: D7.7 fake compatibility gate implemented. `openclaw_service/` remains retained and not delete-ready. Delete only after OpenClaw replacement evidence, MCP compatibility evidence, rollback proof, and approval.

This document authorizes only the explicitly completed delete batches above. It does not physically delete legacy services outside those batches.
