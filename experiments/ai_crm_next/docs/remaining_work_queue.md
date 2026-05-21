# AI-CRM Next Remaining Work Queue

Each task is scoped for a future Codex execution turn. Keep old production services untouched unless the task explicitly reaches a controlled verification phase.

## 1. Run Real PostgreSQL Integration Tests

- objective: Prove Alembic and SQL repos against a real local/test PostgreSQL database.
- files likely involved: `docs/postgres_integration_testing.md`, `scripts/run_postgres_integration_tests.sh`, `tests/integration/*`.
- acceptance criteria: `AICRM_NEXT_TEST_DATABASE_URL=... pytest -q -m postgres_integration` passes; report records DB host/name without password.
- must not do: connect production DB or weaken safety guard.
- suggested validation command: `AICRM_NEXT_TEST_DATABASE_URL=postgresql+psycopg://... .venv/bin/python -m pytest -q -m postgres_integration`.

## 2. Customer Readonly HTTP Dual-Run Against Old Flask

- objective: Compare old Flask and AI-CRM Next customer read APIs over HTTP.
- files likely involved: `tools/readonly_http_dual_run.py`, `docs/readonly_http_dual_run_strategy.md`, `docs/customer_read_model_parity_strategy.md`.
- acceptance criteria: readonly parity report has no blockers; accepted differences documented.
- must not do: run write endpoints or import old Flask app.
- suggested validation command: `.venv/bin/python tools/readonly_http_dual_run.py --old-base-url http://127.0.0.1:5001 --next-testclient --scope customer --output-md /tmp/customer_dual.md --output-json /tmp/customer_dual.json`.

## 3. User Ops Readonly HTTP Dual-Run Against Old Flask

- objective: Compare User Ops overview/list/send-record read shapes over HTTP.
- files likely involved: `tools/readonly_http_dual_run.py`, `docs/readonly_http_dual_run_strategy.md`, `docs/user_ops_parity_strategy.md`.
- acceptance criteria: readonly report passes; write endpoints remain disabled unless isolated.
- must not do: execute real batch send or DND against old production.
- suggested validation command: `.venv/bin/python tools/readonly_http_dual_run.py --old-base-url http://127.0.0.1:5001 --next-testclient --scope user_ops --output-md /tmp/user_ops_dual.md --output-json /tmp/user_ops_dual.json`.

## 4. Questionnaire Real OAuth Security Contract

- objective: Replace fake OAuth contract with a real adapter specification and test harness.
- files likely involved: `../../aicrm_next/questionnaire/oauth.py`, `questionnaire/api.py`, `tests/test_questionnaire_contract.py`.
- acceptance criteria: state validation, callback errors, replay prevention, and masked logs are tested.
- must not do: enable production OAuth without sandbox verification.
- suggested validation command: `.venv/bin/python -m pytest tests/test_questionnaire_contract.py -q`.

## 5. Questionnaire PostgreSQL-Ready Repo

- objective: Add schema/repository boundary for questionnaire definitions and submissions.
- files likely involved: `../../aicrm_next/questionnaire/repo.py`, `migrations/versions/*`, `tests/test_questionnaire_*`.
- acceptance criteria: In-memory and SQL repo shape parity; migration tests exist.
- must not do: migrate production questionnaire data in this task.
- suggested validation command: `.venv/bin/python -m pytest tests/test_questionnaire_contract.py -q`.

## 6. Commerce Real WeChat Pay Adapter Contract

- objective: Define signed WeChat Pay provider adapter behind fake-safe port.
- files likely involved: `commerce/payment_adapters.py`, `commerce/application.py`, `tests/test_commerce_contract.py`.
- acceptance criteria: signing, notify verification, idempotency, and failure modes tested with sandbox/fakes.
- must not do: call real production WeChat Pay.
- suggested validation command: `.venv/bin/python -m pytest tests/test_commerce_contract.py -q`.

## 7. Commerce Real Alipay Adapter Contract

- objective: Define signed Alipay provider adapter behind fake-safe port.
- files likely involved: `commerce/payment_adapters.py`, `commerce/api.py`, `tests/test_commerce_contract.py`.
- acceptance criteria: signed WAP checkout, notify verification, return handling, idempotency tests.
- must not do: mix Alipay logic into WeChat Pay provider implementation.
- suggested validation command: `.venv/bin/python -m pytest tests/test_commerce_contract.py -q`.

## 8. Media Library Storage Adapter

- objective: Add storage port and test implementation for image/attachment/miniprogram assets.
- files likely involved: `media_library/application.py`, `media_library/repo.py`, `tests/test_media_library_contract.py`.
- acceptance criteria: storage abstraction tests, file size/type checks, no real cloud default; `tools/media_library_gray_smoke.py` remains read-only by default and fake writes stay Next-only.
- must not do: upload to production cloud storage.
- suggested validation command: `.venv/bin/python -m pytest tests/test_media_library_contract.py -q`.

## 8A. Media Library Gray-Release Dry Run

- objective: Use the prepared route cutover manifest and gray smoke reports to rehearse Media Library route-level gray release without switching production traffic.
- files likely involved: `docs/gray_rehearsal_batch_1_media_readonly.md`, `docs/gray_rehearsal_batch_1_route_flags.md`, `docs/route_level_gray_release_batches.md`, `docs/route_level_gray_release_runbook.md`, `docs/gray_release_acceptance_checklist.md`, `docs/media_library_gray_release_plan.md`, `docs/media_library_route_cutover_manifest.md`, `tools/run_gray_rehearsal_batch.py`, `tools/media_library_gray_smoke.py`, `tools/generate_gray_release_report.py`, future deployment smoke scripts.
- acceptance criteria: default read-only gray smoke passes; Batch 1 rehearsal report returns `recommendation=GO`; rollback route remains old Flask; no real cloud or WeCom media upload happens.
- must not do: modify Nginx production config or execute old Flask write endpoints.
- suggested validation command: `.venv/bin/python tools/run_gray_rehearsal_batch.py --batch media_readonly --next-testclient --output-md /tmp/gray_rehearsal_batch_1_media_readonly.md --output-json /tmp/gray_rehearsal_batch_1_media_readonly.json`.

## 8G. Route-Level Gray Release Runbook Acceptance

- objective: Review the new Batch 0-6 gray release runbook, proxy pseudo-template, signoff template, acceptance checklist, and report generator before any real route-level execution.
- files likely involved: `docs/route_level_gray_release_batches.md`, `docs/route_level_gray_release_runbook.md`, `docs/route_level_proxy_template.md`, `docs/gray_release_signoff_template.md`, `docs/gray_release_acceptance_checklist.md`, `tools/generate_gray_release_report.py`, `tests/test_gray_release_runbook.py`.
- acceptance criteria: runbook names included/excluded routes, write/external routes are absent from included batches, pseudo template contains no production host/secrets, report generator aggregates blockers and refuses missing JSON.
- must not do: modify production Nginx, switch traffic, connect production DB, or enable real external adapters.
- suggested validation command: `.venv/bin/python -m pytest tests/test_gray_release_runbook.py -q`.

## 8H. Batch 1 Media Readonly Staging Canary Plan

- objective: Prepare the staging or production-like canary plan for Batch 1 Media Library readonly after the local dry-run has passed.
- files likely involved: `docs/staging_canary_topology.md`, `docs/batch_1_media_readonly_canary_plan.md`, `docs/batch_1_media_readonly_canary_runbook.md`, `docs/batch_1_media_readonly_proxy_pseudo_config.md`, `tools/check_batch_1_media_canary_readiness.py`, `tests/test_batch_1_media_canary_readiness.py`.
- acceptance criteria: readiness checker returns `canary_plan_ready`; included routes are GET-only; write routes are excluded; rollback dry-run is present; screenshot baseline exists; side-effect safety remains false for production config changes, real traffic cutover, old writes, cloud upload, and WeCom media upload.
- must not do: modify production Nginx/deploy config, switch real traffic, execute old Flask write endpoints, or enable real cloud/WeCom media adapters.
- suggested validation command: `.venv/bin/python tools/check_batch_1_media_canary_readiness.py --media-smoke-json /tmp/media_gray_smoke_after_canary_plan.json --media-parity-json /tmp/media_parity_after_canary_plan.json --batch-rehearsal-json /tmp/gray_rehearsal_batch_1_media_readonly_audit.json --output-md /tmp/batch_1_media_canary_readiness.md --output-json /tmp/batch_1_media_canary_readiness.json`.

## 8I. Batch 1 Media Readonly Real Staging Proxy Canary

- objective: Repeat Batch 1 Media Library readonly canary against an actual staging proxy or staging base URL after the simulated canary passed.
- files likely involved: `docs/batch_1_media_readonly_canary_execution_report.md`, `docs/batch_1_media_readonly_canary_signoff.md`, `docs/batch_1_media_readonly_canary_runbook.md`, `tools/media_library_gray_smoke.py`, `tools/check_batch_1_media_canary_readiness.py`.
- acceptance criteria: staging proxy/base URL routes all six readonly Media GETs to the intended owner; Media smoke passes; Media parity remains PASS; rollback to old Flask is verified in staging; side-effect safety remains false for production config changes, real traffic cutover, old writes, cloud upload, and WeCom media upload.
- must not do: modify production Nginx/deploy config, enable Media writes, execute old-system writes, upload to real cloud storage, or upload media to real WeCom.
- suggested validation command: `.venv/bin/python tools/media_library_gray_smoke.py --next-base-url <staging-next-or-router-url> --output-md /tmp/media_gray_smoke_real_staging_canary.md --output-json /tmp/media_gray_smoke_real_staging_canary.json`.

## 8B. Product Management Gray-Release Dry Run

- objective: Use the prepared product route cutover manifest and gray smoke reports to rehearse Product Management route-level gray release without switching production traffic.
- files likely involved: `docs/product_management_gray_release_plan.md`, `docs/product_management_route_cutover_manifest.md`, `tools/product_management_gray_smoke.py`, future deployment smoke scripts.
- acceptance criteria: default read-only product gray smoke passes; optional fake-write smoke passes against Next TestClient only; checkout/payment routes remain out of scope; rollback route remains old Flask.
- must not do: modify Nginx production config, execute old Flask write endpoints, run checkout/payment, or call real WeChat Pay/Alipay.
- suggested validation command: `.venv/bin/python tools/product_management_gray_smoke.py --next-testclient --output-md /tmp/product_management_gray_smoke.md --output-json /tmp/product_management_gray_smoke.json`.

## 8J. Batch 2 Product Readonly Real Staging Proxy Canary

- objective: Repeat Batch 2 Product Management readonly canary against an actual staging proxy or staging base URL after the simulated canary passed.
- files likely involved: `docs/batch_2_product_readonly_canary_execution_report.md`, `docs/batch_2_product_readonly_canary_signoff.md`, `docs/batch_2_product_readonly_canary_plan.md`, `docs/batch_2_product_readonly_canary_runbook.md`, `tools/product_management_gray_smoke.py`, `tools/check_batch_2_product_canary_readiness.py`.
- acceptance criteria: staging proxy/base URL routes only the five readonly Product GETs to the intended owner; Product smoke passes; Commerce parity remains PASS; rollback to old Flask is verified in staging; side-effect safety remains false for production config changes, real traffic cutover, old writes, checkout, payment provider calls, and external payment execution.
- must not do: modify production Nginx/deploy config, enable product writes, execute old-system writes, run checkout/payment notify, or call real WeChat Pay/Alipay.
- suggested validation command: `.venv/bin/python tools/product_management_gray_smoke.py --next-base-url <staging-next-or-router-url> --output-md /tmp/product_gray_smoke_real_staging_canary.md --output-json /tmp/product_gray_smoke_real_staging_canary.json`.

## 8C. Customer Read Model Readonly Gray-Release Dry Run

- objective: Use the prepared customer route cutover manifest, sample checklist, and gray smoke reports to rehearse Customer Read Model readonly route-level gray release without switching production traffic.
- files likely involved: `docs/customer_read_model_gray_release_plan.md`, `docs/customer_read_model_route_cutover_manifest.md`, `docs/customer_read_model_sample_data_checklist.md`, `tools/customer_read_model_gray_smoke.py`, future deployment smoke scripts.
- acceptance criteria: default Next-only readonly gray smoke passes; optional old-base-url dual smoke sends only GET; skipped detail/timeline/recent-message routes have explicit no-sample reasons; rollback route remains old Flask.
- must not do: modify Nginx production config, execute old Flask write endpoints, trigger WeCom/archive/tag refresh/OpenClaw, or claim full gray readiness without sample external_userid coverage.
- suggested validation command: `.venv/bin/python tools/customer_read_model_gray_smoke.py --next-testclient --output-md /tmp/customer_read_model_gray_smoke.md --output-json /tmp/customer_read_model_gray_smoke.json`.

## 8K. Batch 3 Customer Readonly Real Staging Proxy Canary

- objective: Repeat Batch 3 Customer Read Model readonly canary against an actual staging proxy or staging base URL after the simulated canary passed.
- files likely involved: `docs/batch_3_customer_readonly_canary_execution_report.md`, `docs/batch_3_customer_readonly_canary_signoff.md`, `docs/batch_3_customer_readonly_canary_plan.md`, `docs/batch_3_customer_readonly_canary_runbook.md`, `tools/customer_read_model_gray_smoke.py`, `tools/readonly_http_dual_run.py`, `tools/check_batch_3_customer_canary_readiness.py`.
- acceptance criteria: staging proxy/base URL routes only readonly Customer GETs to the intended owner; Customer smoke passes; Customer parity remains PASS; readonly dual-run sample-dependent routes execute; rollback to old Flask is verified in staging; side-effect safety remains false for production config changes, real traffic cutover, old writes, WeCom sync, archive sync, tag refresh, and OpenClaw.
- must not do: modify production Nginx/deploy config, enable customer writes, execute old-system writes, connect production PostgreSQL, trigger WeCom/archive/tag refresh/OpenClaw, or use real customer PII.
- suggested validation command: `.venv/bin/python tools/customer_read_model_gray_smoke.py --next-base-url <staging-next-or-router-url> --output-md /tmp/customer_gray_smoke_real_staging_canary.md --output-json /tmp/customer_gray_smoke_real_staging_canary.json`.

## 8D. User Ops Readonly Gray-Release Dry Run

- objective: Use the prepared User Ops route cutover manifest, sample/drift checklist, and gray smoke reports to rehearse User Ops readonly route-level gray release without switching production traffic.
- files likely involved: `docs/user_ops_readonly_gray_release_plan.md`, `docs/user_ops_readonly_route_cutover_manifest.md`, `docs/user_ops_readonly_sample_and_drift_checklist.md`, `docs/batch_4_user_ops_readonly_canary_plan.md`, `tools/user_ops_readonly_gray_smoke.py`, `tools/check_batch_4_user_ops_canary_readiness.py`.
- acceptance criteria: default Next-only readonly gray smoke passes; optional old-base-url dual smoke sends only GET; old missing `激活待录入` is warning/legacy drift when Next has the card; side-effect safety flags remain false; Batch 4 simulated canary evidence and signoff draft are archived.
- must not do: modify Nginx production config, execute old Flask write endpoints, run DND/batch-send/deferred jobs/internal routes, or trigger real WeCom dispatch/media upload.
- suggested validation command: `.venv/bin/python tools/user_ops_readonly_gray_smoke.py --next-testclient --output-md /tmp/user_ops_readonly_gray_smoke.md --output-json /tmp/user_ops_readonly_gray_smoke.json`.

## 8L. Batch 4 User Ops Readonly Real Staging Proxy Canary

- objective: Repeat Batch 4 User Ops readonly canary against an actual staging proxy or staging base URL after the simulated canary passed.
- files likely involved: `docs/batch_4_user_ops_readonly_canary_execution_report.md`, `docs/batch_4_user_ops_readonly_canary_signoff.md`, `docs/batch_4_user_ops_readonly_canary_plan.md`, `docs/batch_4_user_ops_readonly_canary_runbook.md`, `tools/user_ops_readonly_gray_smoke.py`, `tools/readonly_http_dual_run.py`, `tools/check_batch_4_user_ops_canary_readiness.py`.
- acceptance criteria: staging proxy/base URL routes only readonly User Ops GETs to the intended owner; User Ops smoke passes; User Ops parity remains PASS; readonly dual-run has only accepted `激活待录入` legacy drift; rollback to old Flask is verified in staging; side-effect safety remains false for production config changes, real traffic cutover, old writes, DND, batch-send, deferred jobs, WeCom dispatch, and media upload.
- must not do: modify production Nginx/deploy config, enable User Ops writes, execute DND/batch-send/deferred jobs/internal routes, execute old-system writes, or trigger real WeCom dispatch/media upload.
- suggested validation command: `.venv/bin/python tools/user_ops_readonly_gray_smoke.py --next-base-url <staging-next-or-router-url> --output-md /tmp/user_ops_gray_smoke_real_staging_canary.md --output-json /tmp/user_ops_gray_smoke_real_staging_canary.json`.

## 8E. Questionnaire Readonly Gray-Release Dry Run

- objective: Use the prepared Questionnaire route cutover manifest, sample/fake checklist, and gray smoke reports to rehearse Questionnaire admin/public readonly route-level gray release without switching production traffic.
- files likely involved: `docs/questionnaire_readonly_gray_release_plan.md`, `docs/questionnaire_readonly_route_cutover_manifest.md`, `docs/questionnaire_readonly_sample_and_fake_checklist.md`, `docs/batch_5_questionnaire_readonly_canary_plan.md`, `tools/questionnaire_readonly_gray_smoke.py`, `tools/check_batch_5_questionnaire_canary_readiness.py`.
- acceptance criteria: default Next-only readonly gray smoke passes; optional old-base-url dual smoke sends only GET; fake submit is explicit opt-in and Next TestClient only; old WeChat gate/result route drift remains accepted only when Next satisfies the contract; side-effect safety flags remain false; Batch 5 simulated canary evidence and signoff draft are archived.
- must not do: modify Nginx production config, execute old Flask submit/admin write/OAuth callback/external push routes, trigger real OAuth, mutate WeCom tags, or send external webhook pushes.
- suggested validation command: `.venv/bin/python tools/questionnaire_readonly_gray_smoke.py --next-testclient --output-md /tmp/questionnaire_readonly_gray_smoke.md --output-json /tmp/questionnaire_readonly_gray_smoke.json`.

## 8M. Batch 5 Questionnaire Readonly Real Staging Proxy Canary

- objective: Repeat Batch 5 Questionnaire readonly canary against an actual staging proxy or staging base URL after the simulated canary passed.
- files likely involved: `docs/batch_5_questionnaire_readonly_canary_execution_report.md`, `docs/batch_5_questionnaire_readonly_canary_signoff.md`, `docs/batch_5_questionnaire_readonly_canary_plan.md`, `docs/batch_5_questionnaire_readonly_canary_runbook.md`, `tools/questionnaire_readonly_gray_smoke.py`, `tools/check_batch_5_questionnaire_canary_readiness.py`.
- acceptance criteria: staging proxy/base URL routes only readonly Questionnaire GETs to the intended owner; Questionnaire smoke passes; Questionnaire parity remains PASS; accepted legacy drift remains limited to old WeChat gate/result-route differences; rollback to old Flask is verified in staging; side-effect safety remains false for production config changes, real traffic cutover, old writes, submit, OAuth, WeCom tag, and external webhook.
- must not do: modify production Nginx/deploy config, enable Questionnaire writes, execute submit/admin writes/OAuth callbacks, execute old-system writes, trigger WeCom tag mutation, or send external webhooks.
- suggested validation command: `.venv/bin/python tools/questionnaire_readonly_gray_smoke.py --next-base-url <staging-next-or-router-url> --output-md /tmp/questionnaire_gray_smoke_real_staging_canary.md --output-json /tmp/questionnaire_gray_smoke_real_staging_canary.json`.

## 8F. Automation Readonly Staging Canary Follow-Up

- objective: Repeat Batch 6 Automation Conversion readonly canary against an actual staging proxy or staging base URL after the simulated canary passed.
- files likely involved: `docs/batch_6_automation_readonly_canary_execution_report.md`, `docs/batch_6_automation_readonly_canary_signoff.md`, `docs/batch_6_automation_readonly_canary_plan.md`, `docs/batch_6_automation_readonly_canary_runbook.md`, `tools/automation_readonly_gray_smoke.py`, `tools/check_batch_6_automation_canary_readiness.py`.
- acceptance criteria: default readonly gray smoke passes through staging target; optional old-base-url dual smoke sends only GET and uses documented aliases; fake state-machine writes remain explicit opt-in and Next TestClient only; side-effect safety flags remain false for OpenClaw, WeCom, webhook, activation webhook, workflow runtime, and agent runtime.
- must not do: modify Nginx production config, execute old Flask write endpoints, run activation webhook, push OpenClaw context, trigger real WeCom dispatch, call external webhooks, or execute workflow/agent runtime.
- suggested validation command: `.venv/bin/python tools/automation_readonly_gray_smoke.py --next-base-url <staging-next-or-router-url> --output-md /tmp/automation_gray_smoke_real_staging_canary.md --output-json /tmp/automation_gray_smoke_real_staging_canary.json`.

## 8G. Production Canary Approval Human Review

- objective: Review the production canary approval package and decide whether to schedule the first readonly production canary request for Batch 1 Media Library.
- files likely involved: `docs/production_canary_approval_package.md`, `docs/production_canary_change_request_template.md`, `docs/production_canary_observability_plan.md`, `docs/production_canary_rollback_runbook.md`, `tools/check_production_canary_approval_package.py`.
- acceptance criteria: approval checker returns `pending_human_signoff` with no blockers; product owner, engineering owner, ops/deployment owner, rollback owner, and data/security reviewer sign the change request; fresh smoke/parity/readiness evidence is attached.
- must not do: modify production config, cut production traffic, connect real external adapters, enable write routes, or treat simulated evidence as execution approval.
- suggested validation command: `.venv/bin/python tools/check_production_canary_approval_package.py --approval-package docs/production_canary_approval_package.md --batch media_readonly --batch-readiness-json /tmp/batch_1_media_canary_readiness_audit.json --smoke-json /tmp/media_gray_smoke_staging_simulated_canary.json --parity-json /tmp/media_parity_after_canary_execute.json --output-md /tmp/production_canary_approval_media_readonly.md --output-json /tmp/production_canary_approval_media_readonly.json`.

## 8N. Batch 1 Media Production Canary Human Signoff

- objective: Review and complete the Batch 1 Media readonly production canary human signoff packet before any production route flag is enabled.
- files likely involved: `docs/batch_1_media_readonly_human_signoff_submission.md`, `docs/batch_1_media_readonly_production_canary_signoff_packet.md`, `docs/batch_1_media_readonly_production_execution_checklist.md`, `tools/check_batch_1_media_production_signoff_readiness.py`, `docs/production_canary_approval_package.md`.
- acceptance criteria: signoff readiness checker returns `pending_human_signoff` with no blockers; product, engineering, ops/deployment, rollback, and data/security reviewers fill the decision block; execution window and rollback owner are assigned.
- must not do: modify production config, enable route flags, cut traffic, run Media writes, upload to cloud storage, call WeCom media, or treat the packet as execution approval before human signoff.
- suggested validation command: `.venv/bin/python tools/check_batch_1_media_production_signoff_readiness.py --signoff-packet docs/batch_1_media_readonly_production_canary_signoff_packet.md --approval-package docs/production_canary_approval_package.md --readiness-json /tmp/production_canary_approval_media_readonly_audit.json --media-smoke-json /tmp/media_gray_smoke_staging_simulated_canary.json --media-parity-json /tmp/media_parity_after_canary_execute.json --output-md /tmp/batch_1_media_production_signoff_readiness.md --output-json /tmp/batch_1_media_production_signoff_readiness.json`.

## 8O. Batch 1 Media Human Approval Decision

- objective: Humans decide whether to approve, reject, or request changes for the Batch 1 Media readonly production canary using the final submission summary.
- files likely involved: `docs/batch_1_media_readonly_human_signoff_submission.md`, `docs/batch_1_media_readonly_production_canary_signoff_packet.md`, `docs/batch_1_media_readonly_production_execution_checklist.md`.
- acceptance criteria: all required human roles complete the submission fields; decision, conditions, rollback owner, and execution window are recorded.
- must not do: let Codex execute the canary, modify production config, set route flags, route traffic, upload to cloud storage, call WeCom media, or run Media write routes.
- suggested validation command: human review only; no automated production action.

## 8P. Fast Readonly Replacement User Testing Loop

- objective: Move through readonly batches quickly while keeping each batch independently testable and rollbackable.
- files likely involved: `docs/fast_readonly_replacement_execution_plan.md`, `docs/fast_readonly_human_test_tasks.md`, selected batch smoke/parity tools.
- acceptance criteria: exactly one readonly batch is routed at a time; the user completes the matching human test task list; smoke/parity have no blockers; rollback owner stays online.
- must not do: cut multiple batches at once, enable write routes, enable real external adapters, skip user testing, or let Codex perform production route changes automatically.
- suggested validation command: run the selected batch smoke/parity commands listed in `docs/fast_readonly_replacement_execution_plan.md`, then complete the matching section in `docs/fast_readonly_human_test_tasks.md`.

## 9. WeCom Media Adapter

- objective: Add a WeCom media upload adapter contract with fake default and sandbox test plan.
- files likely involved: `integration_gateway/ports.py`, `integration_gateway/fake_adapters.py`, `media_library/*`.
- acceptance criteria: fake adapter remains default; real adapter has config gating and audit.
- must not do: upload media to real WeCom by default.
- suggested validation command: `.venv/bin/python -m pytest tests/test_media_library_contract.py tests/test_architecture_boundaries.py -q`.

## 10. OpenClaw Real Webhook Adapter

- objective: Replace fake push preview with a gated real OpenClaw webhook adapter.
- files likely involved: `automation_engine/application.py`, `integration_gateway/ports.py`, `integration_gateway/fake_adapters.py`.
- acceptance criteria: payload compatibility, auth, retry, failure audit, fake default tests.
- must not do: send real webhook without explicit config and sandbox.
- suggested validation command: `.venv/bin/python -m pytest tests/test_automation_conversion_contract.py -q`.

## 11. Automation Workflow Runtime Phase 2

- objective: Add workflow scheduling/runtime semantics on top of the six-pool state machine.
- files likely involved: `automation_engine/workflow.py`, `automation_engine/application.py`, `tests/test_automation_conversion_contract.py`.
- acceptance criteria: runtime is idempotent, records execution, respects silent/converted/exited pools.
- must not do: call real WeCom/OpenClaw.
- suggested validation command: `.venv/bin/python -m pytest tests/test_automation_conversion_contract.py -q`.

## 12. Production Deployment Smoke Harness

- objective: Create repeatable route-level smoke commands for AI-CRM Next deployment.
- files likely involved: `tools/capture_frontend_screenshots.py`, `docs/frontend_route_manifest.md`, `docs/frontend_screenshot_baseline.md`, `docs/production_replacement_route.md`, future `scripts/`.
- acceptance criteria: health, admin routes, API read routes, and frontend adapters checked in one command; current 14-route Playwright PNG baseline remains reproducible and is extended to deployment HTTP mode.
- must not do: change business behavior.
- suggested validation command: `.venv/bin/python tools/capture_frontend_screenshots.py --output-dir artifacts/frontend_screenshots --mode testclient --output-md /tmp/aicrm_next_frontend_route_screenshot_baseline.md --output-json /tmp/aicrm_next_frontend_route_screenshot_baseline.json`.

## 13. Data Migration / Backfill Design

- objective: Design how old Flask data maps into AI-CRM Next PostgreSQL tables and repos.
- files likely involved: `docs/migration_strategy.md`, new migration design doc, `migrations/versions/*`.
- acceptance criteria: source/target tables, ordering, idempotency, rollback, and sample verification are documented.
- must not do: run production migration.
- suggested validation command: documentation review plus dry-run fixture tests.

## 14. Observability / Audit / Idempotency Hardening

- objective: Make writes traceable and replay-safe before shadow-write or production use.
- files likely involved: `platform_foundation/audit.py`, `platform_foundation/idempotency.py`, API modules.
- acceptance criteria: correlation IDs, audit records, idempotency keys, and failure logs are tested.
- must not do: introduce cross-module hidden writes.
- suggested validation command: `.venv/bin/python -m pytest tests/test_*contract.py -q`.
