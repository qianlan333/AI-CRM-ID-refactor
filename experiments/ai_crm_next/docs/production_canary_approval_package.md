# Production Canary Approval Package

## Executive Summary

AI-CRM Next has entered the production canary approval package stage. This package collects readonly route-level evidence for requesting a controlled production canary review.

This is not a production cutover. No production route has been enabled, no production proxy/deploy configuration has been modified, and no production traffic has been routed to AI-CRM Next. All Batch 1-6 records are local, staging, or staging-simulated evidence. A real production canary requires fresh evidence, an approved change request, and human signoff before any route flag or proxy rule can be changed.

Current approval status: `pending_human_signoff`.

## Evidence Summary

| evidence | status | source |
| --- | --- | --- |
| ordinary pytest | PASS | latest local run: `361 passed, 3 skipped` |
| six parity reports | PASS | User Ops, Customer Read Model, Questionnaire, Automation, Commerce, Media |
| real PostgreSQL integration | PASS for local test DB | `docs/real_postgres_integration_run.md` |
| frontend PNG screenshot baseline | PASS | `docs/frontend_screenshot_baseline.md`, `artifacts/frontend_screenshots/route_status.json` |
| readonly HTTP dual-run | PASS with documented legacy drift | `docs/real_readonly_http_dual_run.md` |
| Batch 1 Media readonly | staging-simulated evidence available | `docs/batch_1_media_readonly_canary_execution_report.md` |
| Batch 1 Media production signoff packet | pending human signoff | `docs/batch_1_media_readonly_production_canary_signoff_packet.md` |
| Batch 2 Product readonly | staging-simulated evidence available | `docs/batch_2_product_readonly_canary_execution_report.md` |
| Batch 3 Customer readonly | staging-simulated evidence available | `docs/batch_3_customer_readonly_canary_execution_report.md` |
| Batch 4 User Ops readonly | staging-simulated evidence available | `docs/batch_4_user_ops_readonly_canary_execution_report.md` |
| Batch 5 Questionnaire readonly | staging-simulated evidence available | `docs/batch_5_questionnaire_readonly_canary_execution_report.md` |
| Batch 6 Automation readonly | staging-simulated evidence available | `docs/batch_6_automation_readonly_canary_execution_report.md` |

## Batch Readiness Table

| batch | module | canary_status | execution_mode | readiness_checker | smoke_result | parity_result | side_effect_safety | legacy_drift | production_approval_status | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Batch 1 | Media readonly | staging_simulated_canary_pass | staging_simulated | PASS | PASS | PASS | all false | none blocking | pending_human_signoff | Lowest-risk first canary candidate. |
| Batch 2 | Product readonly | staging_simulated_canary_pass | staging_simulated | PASS | PASS | PASS | all false | none blocking | pending_human_signoff | Checkout/payment excluded. |
| Batch 3 | Customer readonly | staging_simulated_canary_pass | staging_simulated + old GET dual evidence | PASS | PASS | PASS | all false | old admin login redirect accepted | pending_human_signoff | Uses masked local customer sample. |
| Batch 4 | User Ops readonly | staging_simulated_canary_pass | staging_simulated + old GET dual evidence | PASS | PASS | PASS | all false | old missing `激活待录入` accepted | pending_human_signoff | DND, batch-send, deferred jobs excluded. |
| Batch 5 | Questionnaire readonly | staging_simulated_canary_pass | staging_simulated + old GET dual evidence | PASS | PASS | PASS | all false | old WeChat gate/result route drift accepted | pending_human_signoff | Submit, OAuth, WeCom tag, webhook excluded. |
| Batch 6 | Automation readonly | staging_simulated_canary_pass | staging_simulated + old GET alias evidence | PASS | PASS | PASS | all false | old route alias/admin auth drift accepted | pending_human_signoff | Manual writes, activation webhook, OpenClaw, workflow runtime excluded. |

## Accepted Legacy Drift

| module | drift | why accepted | production risk | mitigation | validation evidence |
| --- | --- | --- | --- | --- | --- |
| User Ops | old Flask overview lacks `激活待录入` | Next satisfies the current 8-card contract; old gap is legacy behavior | Operators may see a card count difference during comparison | Monitor Next overview card integrity and keep old drift documented in signoff | Batch 4 smoke/readiness reports; `docs/user_ops_readonly_sample_and_drift_checklist.md` |
| Customer | old `/admin/customers` can redirect to login | Page-layer admin auth redirect is not an API read-model blocker; Next page stays 200 | Canary page checks may see old 302 during rollback verification | Treat old page redirect as expected legacy auth behavior; API routes remain the primary dual evidence | Batch 3 smoke/readiness reports; `docs/customer_read_model_gray_release_plan.md` |
| Questionnaire | old non-WeChat public API can return `403 please_open_in_wechat`; old result route differs from Next JSON result route | Next satisfies the readonly API/page contract; old public behavior is environment/route-shape drift | Public route comparison may show old-side 403/404 in non-WeChat canary checks | Use route-specific expected status, validate Next JSON result contract, do not enable submit/OAuth | Batch 5 smoke/readiness reports; `docs/questionnaire_readonly_sample_and_fake_checklist.md` |
| Automation | old exact Next-style readonly APIs can be missing; old aliases return legacy payloads; old admin page may redirect unauthenticated users | Old route aliases provide GET-only evidence while Next contract remains stable | Canary comparison may produce old-side shape warnings or 302 for page auth | Use documented old aliases, keep exact old missing routes as legacy drift, monitor Next required shape | Batch 6 smoke/readiness reports; `docs/automation_readonly_route_cutover_manifest.md` |

## Current No-Go Items

- Production PostgreSQL is not connected.
- Real production canary has not been executed.
- Real WeCom is not connected.
- Real OAuth is not connected.
- Real payment providers are not connected.
- Real OpenClaw is not connected.
- Real cloud storage and WeCom media upload are not connected.
- This approval package supports only readonly production canary review. It does not support write route cutover.
- No batch may be routed to production without fresh smoke/parity/readiness evidence.
- No batch may be routed to production without human signoff and rollback owner assignment.

## Recommended First Production Canary

Recommended first candidate: Batch 1 Media readonly.

Reasons:

- It has the lowest external side-effect risk.
- It already has local rehearsal, staging-simulated canary evidence, a canary plan, and a readiness checker.
- It does not involve payment, OAuth, WeCom dispatch, OpenClaw, workflow runtime, or customer data writes.
- The readonly route scope is small and clear.
- Rollback is route-flag based and does not require destructive database operations.

Human signoff materials for this candidate are prepared in `docs/batch_1_media_readonly_production_canary_signoff_packet.md` and `docs/batch_1_media_readonly_production_execution_checklist.md`. Their status is `pending_human_signoff`; they do not apply production route flags, modify production config, or route production traffic.

## Required Human Signoff

| role | required before production canary | notes |
| --- | --- | --- |
| product owner | yes | Confirms user-facing route scope and acceptable legacy drift. |
| engineering owner | yes | Confirms Next route owner and safety checks. |
| ops/deployment owner | yes | Owns proxy/route flag execution and evidence capture. |
| rollback owner | yes | Must be available during the entire canary window. |
| data/security reviewer | yes | Confirms no production data migration/write/external risk. |
| external adapter owner | conditional | Required before any batch involving real external services; all current readonly batches keep real adapters disabled. |

## Approval Boundary

Approval package status: `ready_for_human_review`.

Production canary status remains `pending_human_signoff`. This package does not authorize production route changes by itself.
