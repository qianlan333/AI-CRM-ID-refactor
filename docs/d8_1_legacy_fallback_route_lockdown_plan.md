# D8.1 Legacy Fallback Route Lockdown Plan

D8.1 is a planning and readiness gate for legacy Flask fallback route lockdown. It does not delete the legacy shell, does not modify production config, and does not cut traffic.

## Goal

- Keep the old Flask fallback available for explicit emergency and write/external fallback use.
- Prevent the old Flask fallback from silently serving readonly owner routes that AI-CRM Next already owns.
- Define route lockdown categories, retired readonly denylist scope, allowed fallback scope, checker behavior, and future enforcement rules.
- Keep `legacy_flask_app.py`, `wecom_ability_service/`, and `openclaw_service/` in place.

Correct D8.1 status:

| item | value |
| --- | --- |
| `legacy_fallback_lockdown_status` | `planning_ready` |
| `legacy_shell_deleted` | false |
| `production_config_modified` | false |
| `production_cutover_executed` | false |
| deletion readiness | false |

## Lockdown Categories

| category | meaning | D8.1 action |
| --- | --- | --- |
| `allowed_fallback` | Explicit fallback routes that may remain available for emergency operations or not-yet-cut-over external behavior | document and check that the route is intentionally allowed |
| `retired_readonly_route` | D1-D6 readonly owner routes already moved to AI-CRM Next | treat any legacy registration as a blocker |
| `write_external_fallback` | Write, external, webhook, provider, runtime, sync, or dispatch routes whose real Next production path is not cut over | allowed only as fallback, never as production owner |
| `diagnostic_only` | Health, audit, route diagnostics, API docs, and operational inspection helpers | allowed while explicitly scoped |
| `blocked_by_default` | Routes not classified as allowed fallback, diagnostics, or retained mixed fallback | future enforcement should block until reviewed |
| `needs_manual_review` | Ambiguous mixed routes where GET pages and write/runtime actions share a module | require D8.2 implementation decision before hard enforcement |

## Retired Readonly Routes

The retired readonly set must cover D1-D6:

- Media readonly: image library, attachment library, miniprogram library readonly/admin/API routes.
- Product readonly: product management pages and product admin APIs.
- Customer readonly: customer list/detail/timeline read model routes.
- User Ops readonly: user ops overview/list/send-record routes.
- Questionnaire readonly: admin questionnaire readonly pages/APIs, public GET form/result routes, and H5 GET questionnaire payload.
- Automation readonly: automation overview/pools/members/execution-records and legacy readonly aliases.

These routes should not be registered by legacy Flask fallback. If the D8.1 checker finds one still registered, the result is a blocker.

## Allowed Fallback Route Types

Allowed fallback does not mean legacy is production owner. The following may remain registered until their replacement evidence and rollback gates are complete:

- Legacy run/help/init-db fallback.
- Old write/external fallback not yet production cut over.
- Payment checkout, notify, return, transaction, and provider fallback not yet replaced in production.
- OAuth fallback not yet replaced in production.
- Archive sync, contacts sync, identity, and projection fallback not yet production cut over.
- OpenClaw legacy bridge and MCP compatibility fallback not yet retired.
- Operational diagnostics, jobs, audit, and health surfaces if still needed.

## Checker Strategy

D8.1 checker must:

- Read `docs/d8_1_legacy_fallback_route_matrix.md`.
- Build a static legacy Flask route map by scanning `bp.route(...)` registrations under `wecom_ability_service/http/`.
- Fail if any `retired_readonly_route` row is marked `legacy_registration_expected=true`.
- Fail if a retired readonly route pattern is still registered by legacy Flask.
- Keep allowed fallback routes as documented fallback only.
- Confirm `app.py` still defaults to AI-CRM Next.
- Confirm `legacy_flask_app.py`, `wecom_ability_service/`, and `openclaw_service/` still exist.
- Confirm production/deploy/nginx/systemd config files are not modified.
- Confirm docs avoid forbidden approval markers.

## D8.2 Implementation Handoff

D8.2 is the earliest phase that may implement route lockdown behavior such as code-level hard block, 410 response, denylist enforcement, or fallback registration flags.

D8.1 does not implement that enforcement. It only prepares the plan, route matrix, checker, and tests. Any enforcement must be a separate change with its own rollback plan.

The D8.2 implementation now follows this handoff: the legacy Flask fallback registers a runtime guard that blocks retired D1-D6 readonly routes with a stable 410 response while allowing documented write/external fallback and diagnostic routes. The default AI-CRM Next runtime remains unchanged.
