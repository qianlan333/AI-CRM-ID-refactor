# Next Production Gap Closure Report

## Scope

This change closes the immediate production runtime gap where AI-CRM Next was the default route owner but still exposed fixture-backed health and fixture-backed admin/read surfaces.

The implementation keeps the existing legacy code and 5013 callback fallback in place. Production routes are owned by Next and, when production mode or a real `DATABASE_URL` is detected, Next uses a compatibility facade to call the existing legacy Flask domain/runtime code.

## Runtime Guard

- `/health` now reports `database_mode`, `fixture_mode`, `production_data_ready`, and `runtime_owner`.
- Production fixture mode is reported as degraded instead of silently healthy.
- Local fixture mode remains supported for tests and development.

## Production Data Access

- Production runtime no longer treats fixture health as a successful production-data state.
- Customer read-model APIs use a dedicated Next integration gateway boundary (`legacy_customer_read_facade`) so production reads go through the legacy domain query layer and PostgreSQL instead of fixture rows.
- Callback, timer, payment/OAuth, commerce, media, and selected automation compatibility paths are routed through the Next production compatibility facade where legacy domain/runtime behavior is still required.
- Native Next questionnaire, media, commerce, and automation read surfaces remain route-owned by Next and are covered by the route compatibility checker for non-404 production entry behavior; deeper production-data verification is part of the server validation step.
- The facade preserves Next route-owner headers and adds `X-AICRM-Compatibility-Facade: legacy_flask_facade`.
- Legacy Flask remains the domain/service compatibility boundary; no legacy code was deleted.

## Callback And Timer Coverage

- Next now owns `/wecom/external-contact/callback` and `/api/wecom/events` through `aicrm_next.integration_gateway.wecom_callback_facade`.
- 5013 callback fallback remains required until a real observation window passes.
- Timer endpoints are Next-owned through the facade and protected by `AUTOMATION_INTERNAL_API_TOKEN` before forwarding:
  - `/api/admin/automation-conversion/reply-monitor/run-due`
  - `/api/admin/automation-conversion/reply-monitor/capture`
  - `/api/admin/automation-conversion/jobs/run-due`
  - `/api/admin/cloud-orchestrator/campaigns/run-due`

## Safety Status

- No production Nginx/systemd/deploy config was changed in repository code.
- No production timer is automatically enabled by this PR.
- No real WeCom, payment, OAuth, or OpenClaw external call is executed by tests or checkers.
- No module is marked as production approved.

## Remaining Runtime Validation

- Deploy to server through GitHub.
- Confirm `/health` reports `database_mode=postgres`, `fixture_mode=false`, `production_data_ready=true`.
- Confirm key admin pages and APIs return non-404 and production records.
- Run timer readiness checker on the server before enabling paused timers.
- Keep 5013 callback fallback until callback observation evidence is collected.
