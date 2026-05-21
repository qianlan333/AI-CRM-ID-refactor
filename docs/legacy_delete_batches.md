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

Checkout, payment return, and payment notify routes remain legacy fallback and are not delete-ready. Product admin write fallback routes went down with the Product Management owner, but this does not make Next product writes `production_ready`.

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

D6 Automation old readonly routes have not started.

## D6: Automation Old Readonly Routes

Status: not started. Delete only after Automation readonly production evidence and accepted legacy route drift review.

## D7: Write And External Adapters

Status: not started. Delete only after real write/external replacement evidence and explicit provider approval.

## D8: Old Flask App Factory And HTTP Registrar

Status: not started. Delete only after all legacy routes are retired and rollback no longer depends on Flask.

## D9: OpenClaw Legacy Adapter Retirement

Status: not started. Delete only after OpenClaw replacement evidence and approval.

This document authorizes only the explicitly completed delete batches above. It does not physically delete legacy services outside those batches.
