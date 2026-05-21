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

D3 Customer old readonly routes have not started.

## D3: Customer Old Readonly Routes

Status: not started. Delete only after Customer readonly production evidence, including detail/timeline/recent-message proof.

## D4: User Ops Old Readonly Routes

Status: not started. Delete only after User Ops readonly production evidence and accepted legacy drift review.

## D5: Questionnaire Old Readonly Routes

Status: not started. Delete only after Questionnaire readonly production evidence. Submit, OAuth, WeCom tag, and webhook routes are excluded.

## D6: Automation Old Readonly Routes

Status: not started. Delete only after Automation readonly production evidence and accepted legacy route drift review.

## D7: Write And External Adapters

Status: not started. Delete only after real write/external replacement evidence and explicit provider approval.

## D8: Old Flask App Factory And HTTP Registrar

Status: not started. Delete only after all legacy routes are retired and rollback no longer depends on Flask.

## D9: OpenClaw Legacy Adapter Retirement

Status: not started. Delete only after OpenClaw replacement evidence and approval.

This document authorizes only the explicitly completed delete batches above. It does not physically delete legacy services outside those batches.
