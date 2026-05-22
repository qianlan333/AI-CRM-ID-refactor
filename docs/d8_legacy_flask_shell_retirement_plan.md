# D8 Legacy Flask Shell Retirement Plan

Status: planning/readiness only.

This D8.0 plan restarts legacy Flask shell retirement planning from the current `main` branch after D7 slim cleanup. It does not retire the shell, does not move the Flask app factory, does not create a `legacy_flask/` archive package, and does not change runtime behavior.

## Current Runtime Boundary

| Area | Current owner | D8.0 decision |
| --- | --- | --- |
| Default runtime | `app.py` -> root `aicrm_next/` | Keep AI-CRM Next as default runtime. |
| Explicit legacy fallback runner | `legacy_flask_app.py` | Keep. |
| Legacy Flask app factory | `wecom_ability_service/__init__.py` | Keep in place. |
| Legacy route registrar | `wecom_ability_service/routes.py`, `wecom_ability_service/http/__init__.py` | Keep in place. |
| Legacy external fallback | payment, OAuth, WeCom, archive, contacts, identity, workflow fallback files plus fake OpenClaw/MCP adapter boundary | Keep blocked and available; repo-side `openclaw_service/` is absent after D9.6. |

## Non Goals

- No D8 shell deletion.
- No D8.2-D8.5 work.
- No `legacy_flask/` package creation.
- No app factory migration.
- No runtime route lockdown implementation.
- No production/deploy/nginx/systemd changes.
- No real external service calls.
- No write endpoint execution.

## D8 Deletion Gate

D8 shell removal cannot proceed until all of the following are true and reviewed:

| Gate | Required evidence |
| --- | --- |
| D7 real external replacement evidence | Each D7 write/external/runtime/payment/OAuth/WeCom/OpenClaw/archive/contacts/identity capability has real adapter evidence, not only fake contracts. |
| Production observation window | Production traffic has been observed for an approved window without legacy fallback dependence. |
| No legacy route hits | Route-owner telemetry shows no legacy Flask route hits for the retired surface. |
| Rollback no longer requires Flask shell | Rollback plans no longer depend on `legacy_flask_app.py` or the legacy Flask app factory. |
| Deploy/systemd Next-only path | Deployment and process supervision have an approved Next-only path with rollback proof. |
| Human signoff | Explicit human approval is recorded for shell retirement. |

## Planning Checklist

| Check | Expected D8.0 state |
| --- | --- |
| `legacy_flask_app.py` exists | yes |
| `wecom_ability_service/` exists | yes |
| `openclaw_service/` repo path | absent after D9.6 physical deletion record |
| `app.py` default runtime remains Next | yes |
| Legacy fallback usage remains explicit | yes |
| D8.1 route/fallback matrix is planning-only | yes |
| D8.2-D8.5 artifacts are absent unless separately approved | yes |

## Verification

D8.0 planning is verified by `tools/check_d8_legacy_shell_retirement_readiness.py` and `tests/test_d8_legacy_shell_retirement_readiness.py`. The checker validates planning artifacts and protected fallback presence only; it does not execute write endpoints, external calls, or runtime route enforcement.
