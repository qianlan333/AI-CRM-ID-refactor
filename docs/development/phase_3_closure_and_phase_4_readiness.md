# Phase 3 Closure And Phase 4 Readiness

Status: Phase 3 closure/readiness only. This report does not change runtime,
delete fallback, narrow `production_compat`, enable real external calls, mark
any route as `delete_ready`, or authorize Phase 4 to start automatically.

## Phase 3A-F Matrix

| Phase | Route | Capability owner | Kind | Runtime changed | Exact Next owner confirmed | Fallback retained | Production unavailable behavior | Fixture fake success blocked | Checker | Business continuity status | Delete ready |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Phase 3A | `GET /api/sidebar/contact-binding-status` | `aicrm_next.identity_contact` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3_sidebar_readonly_replacement.py` | accepted with fallback retained | false |
| Phase 3A | `GET /api/sidebar/customer-context` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3_sidebar_readonly_replacement.py` | accepted with fallback retained | false |
| Phase 3B | `GET /api/admin/customers/profile` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3b_customer_profile_readonly.py` | accepted with fallback retained | false |
| Phase 3B | `GET /api/admin/customers/profile/tags` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3b_customer_profile_readonly.py` | accepted with fallback retained | false |
| Phase 3C | `GET /api/customers` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3c_customer_read_model_readonly.py` | accepted with fallback retained | false |
| Phase 3C | `GET /api/customers/{external_userid}` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3c_customer_read_model_readonly.py` | accepted with fallback retained | false |
| Phase 3C | `GET /api/customers/{external_userid}/timeline` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3c_customer_read_model_readonly.py` | accepted with fallback retained | false |
| Phase 3D | `GET /api/messages/{external_userid}/recent` | `aicrm_next.customer_read_model` | readonly_api | false | true | true | degraded/error | true | `tools/check_phase3d_recent_messages_readonly.py` | accepted with fallback retained | false |
| Phase 3E | Phase 3 readonly acceptance report | `aicrm_next.platform_foundation` | acceptance_only | false | n/a | true | n/a | true | `tools/check_phase3_readonly_acceptance.py` | report-only acceptance completed | false |
| Phase 3F | `GET /admin/customers` | `aicrm_next.frontend_compat + aicrm_next.customer_read_model` | readonly_shell_navigation | false | true | true | degraded/page_error | true | `tools/check_phase3f_admin_customers_shell.py` | accepted with fallback retained | false |

## Phase 3 Closure Decision

Recommended closure decision:

- Phase 3 customer/sidebar readonly track: closeable.
- Phase 3 does not authorize fallback removal.
- Phase 3 does not authorize production cutover.
- Phase 3 does not authorize write replacement.
- Remaining readonly/shell candidates are deferred unless separately approved.

This closure decision is scoped to the customer/sidebar readonly and
shell/navigation hardening completed in Phase 3A-F. It does not change route
registration, `production_compat`, legacy fallback, deploy configuration, or
production database schema.

## Remaining Deferred Readonly/Shell Candidates

### `GET /admin`

- Why deferred: It is a shell/navigation surface with low direct side-effect
  risk, but Phase 3G is closure/readiness only and should not expand functional
  hardening.
- Daily business impact: Yes. It is an admin entry path and must stay available.
- External side effect: None in the shell/navigation scope.
- Fallback retention: Keep existing behavior until parity, checker, smoke,
  rollback, and owner approval are complete in a separate PR.

### `GET /admin/questionnaires`

- Why deferred: The page can be evaluated as readonly admin navigation, but the
  surrounding questionnaire family has submit, OAuth, public H5, diagnostics,
  and admin write paths that must stay explicitly excluded.
- Daily business impact: Yes. Questionnaire admin and public questionnaire use
  are daily-business-sensitive.
- External side effect: None for readonly page evaluation, but adjacent OAuth
  and external push paths are excluded.
- Fallback retention: Keep existing behavior until parity, checker, smoke,
  rollback, and owner approval are complete in a separate PR.

### `GET /sidebar/bind-mobile` Shell/Page Only

- Why deferred: The shell/page can be evaluated separately, but the adjacent
  bind-mobile API is a write path and must not enter Phase 3 closure scope.
- Daily business impact: Yes. It is part of sidebar daily usage.
- External side effect: None for shell/page evaluation; adjacent mobile binding
  write behavior remains excluded.
- Fallback retention: Keep existing behavior until parity, checker, smoke,
  rollback, and owner approval are complete in a separate PR.

## Phase 4 Readiness Gate

Phase 4 can only address internal_write candidates and cannot start
automatically from this report. It requires explicit owner approval and a
separate PR for the selected first candidate.

Phase 4 first batch must not include:

- Payment
- OAuth
- WeCom external calls
- timer
- automation execution
- media upload
- OpenClaw / MCP real external calls

Every Phase 4 first-batch candidate must satisfy all of these before
implementation:

- no real external side effect
- bounded internal write only
- idempotency or duplicate protection defined
- audit/operator identity defined or explicitly not required
- rollback data path defined
- dry-run or preview mode if business impact exists
- fallback retained
- production smoke defined
- checker defined
- does not block daily business use

## Phase 4 Suggested First Candidates

These are evaluation candidates only. This report does not implement them and
does not authorize Phase 4 to start.

### Customer Profile Readonly-Adjacent Internal Metadata Update

- Why candidate: Potentially bounded customer/profile internal metadata update
  work, if confirmed internal-only and no real external call exists.
- Excluded side effects: Payment, OAuth, WeCom external call, timer, automation
  execution, media upload, OpenClaw/MCP real external call.
- Required guardrails: idempotency or duplicate protection, audit/operator
  identity, checker, production smoke, dry-run or preview if business impact
  exists, fallback retained.
- Rollback requirement: Define data rollback or compensating update before
  implementation; retain fallback until rollback is proven.
- Daily business continuity requirement: Must not block customer, sidebar,
  profile, or customer-list daily use.

### Questionnaire Admin Draft Save/Update Only

- Why candidate: Potentially bounded questionnaire draft persistence, if
  external push, OAuth, public submit, diagnostics write, and production cutover
  are explicitly excluded.
- Excluded side effects: external push, OAuth, public submit, diagnostics write,
  Payment, WeCom external call, timer, automation execution, media upload,
  OpenClaw/MCP real external call.
- Required guardrails: idempotency or duplicate protection, audit/operator
  identity, checker, production smoke, dry-run or preview if business impact
  exists, fallback retained.
- Rollback requirement: Define draft restore or revert path before
  implementation; retain fallback until rollback is proven.
- Daily business continuity requirement: Must not interrupt current
  questionnaire admin or public questionnaire daily paths.

### Automation Profile-Segment-Template Internal CRUD Only

- Why candidate: Potentially bounded template metadata CRUD, if no run-due,
  execution, send, timer, or external assistant call is included.
- Excluded side effects: run-due, send, timer, automation execution, Payment,
  OAuth, WeCom external call, media upload, OpenClaw/MCP real external call.
- Required guardrails: idempotency or duplicate protection, audit/operator
  identity, checker, production smoke, dry-run or preview if business impact
  exists, fallback retained.
- Rollback requirement: Define template restore or revert path before
  implementation; retain fallback until rollback is proven.
- Daily business continuity requirement: Must not interrupt current automation
  workspace daily use or execution-safe mode.
