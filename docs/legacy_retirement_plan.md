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

Checkout, payment provider, return, notify, and transaction management remain legacy fallback and are not delete-ready. Product admin write fallback routes retire with the old Product Management owner, but Next product writes are still not `production_ready`. Rollback is `git revert` of the D2 PR or restoring a pre-D2 fallback tag.

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
