# Legacy Delete Batches

Deletion is intentionally separated from the runtime switch.

## D0: Freeze Only

- Mark `wecom_ability_service/` as legacy fallback.
- Mark `openclaw_service/` as legacy adapter/reference.
- Switch `app.py run` to AI-CRM Next.
- Keep `run-legacy` and `legacy_flask_app.py`.

## D1: Media Old Readonly Routes

Delete only after Media readonly production evidence and rollback proof.

## D2: Product Old Readonly Routes

Delete only after Product readonly production evidence. Checkout and payment notify remain excluded until separately approved.

## D3: Customer Old Readonly Routes

Delete only after Customer readonly production evidence, including detail/timeline/recent-message proof.

## D4: User Ops Old Readonly Routes

Delete only after User Ops readonly production evidence and accepted legacy drift review.

## D5: Questionnaire Old Readonly Routes

Delete only after Questionnaire readonly production evidence. Submit, OAuth, WeCom tag, and webhook routes are excluded.

## D6: Automation Old Readonly Routes

Delete only after Automation readonly production evidence and accepted legacy route drift review.

## D7: Write And External Adapters

Delete only after real write/external replacement evidence and explicit provider approval.

## D8: Old Flask App Factory And HTTP Registrar

Delete only after all legacy routes are retired and rollback no longer depends on Flask.

## D9: OpenClaw Legacy Adapter Retirement

Delete only after OpenClaw replacement evidence and approval.

This is a delete plan only. This PR does not physically delete legacy services.
