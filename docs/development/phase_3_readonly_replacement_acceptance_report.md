# Phase 3 Readonly Replacement Acceptance Report

Status: Phase 3A-D acceptance report only. This document does not change runtime behavior.
It does not delete fallback, narrow `production_compat`, enable real external
calls, or mark any route as `delete_ready`.

## Acceptance Matrix

| Phase | Route | Method | Capability owner | Endpoint module | Category | Production behavior | Fallback retained | Checker | Production unavailable | Fixture success blocked | Business continuity | Delete ready |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Phase 3A | `/api/sidebar/contact-binding-status` | GET | `aicrm_next.identity_contact` | `aicrm_next.identity_contact.api` | readonly | readonly_facade | true | `tools/check_phase3_sidebar_readonly_replacement.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3A | `/api/sidebar/customer-context` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly | readonly_facade | true | `tools/check_phase3_sidebar_readonly_replacement.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3B | `/api/admin/customers/profile` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly | readonly_facade | true | `tools/check_phase3b_customer_profile_readonly.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3B | `/api/admin/customers/profile/tags` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly | readonly_facade | true | `tools/check_phase3b_customer_profile_readonly.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3C | `/api/customers` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly | readonly_facade | true | `tools/check_phase3c_customer_read_model_readonly.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3C | `/api/customers/{external_userid}` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly | readonly_facade | true | `tools/check_phase3c_customer_read_model_readonly.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3C | `/api/customers/{external_userid}/timeline` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly | readonly_facade | true | `tools/check_phase3c_customer_read_model_readonly.py` | degraded/error | true | accepted with fallback retained | false |
| Phase 3D | `/api/messages/{external_userid}/recent` | GET | `aicrm_next.customer_read_model` | `aicrm_next.customer_read_model.api` | readonly_customer_archive | readonly_facade | true | `tools/check_phase3d_recent_messages_readonly.py` | degraded/error | true | accepted with fallback retained | false |

## Acceptance Conditions

Each accepted route must continue to satisfy:

- Next exact owner confirmed.
- No route-level legacy forward for the exact route.
- No `X-AICRM-Compatibility-Facade: legacy_flask_facade` response header on the
  exact route.
- Legacy production fallback retained.
- Production unavailable returns degraded/error.
- No fixture/local_contract/demo fake success in production probes.
- No real external side effect.
- Rollback is revert of the specific Phase 3 PR.
- `delete_ready` remains false.

## Business Continuity

The current customer list, customer detail, customer timeline, customer recent
messages, WeCom sidebar binding status, sidebar customer context, customer
profile, and customer profile tags daily paths must not be affected by Phase 3
acceptance work.

Fallback remains required until parity, checker, smoke, rollback, and owner approval are all satisfied.
Architecture convergence must not cause 404, 500, empty-data false success, or
accidental external side effects.

## Remaining Constraints

- Do not delete `legacy_customer_read_facade`.
- Do not delete `production_compat`.
- Do not narrow the `/api/messages*` wildcard.
- Do not enable real archive sync.
- Do not process write routes.
- Do not enter Payment, OAuth, WeCom, timer, or automation execution work.

## Suggested Next Low-Risk Candidates

These are evaluation candidates only. This report does not authorize runtime
changes.

### Shell/Navigation Candidates

- `/admin`: low-risk because it is a shell/navigation surface. It has no direct
  external side effect in this candidate scope. It is a daily business path, so
  fallback must remain until parity, checker, smoke, rollback, and owner approval
  are complete.
- `/admin/customers`: low-risk as a customer admin shell/navigation surface, not
  a write/API replacement. It has no direct external side effect in this
  candidate scope. It is a daily customer operations path, so fallback must
  remain until parity, checker, smoke, rollback, and owner approval are complete.
- `/sidebar/bind-mobile`: only the shell/page aspect is a candidate; the
  adjacent bind-mobile write API is out of scope. It has no external side effect
  in the shell/page scope, but it is a daily sidebar path, so fallback must
  remain until parity, checker, smoke, rollback, and owner approval are complete.

### Readonly Admin Page Candidate

- `/admin/questionnaires`: low-risk only as a readonly admin page candidate.
  Questionnaire submit, OAuth, public H5 write, and diagnostics write paths are
  not in the next-step scope. It is a daily admin path, so fallback must remain
  until parity, checker, smoke, rollback, and owner approval are complete.

### Defer Candidates

- Payment, OAuth, WeCom, media upload, timer, and automation execution remain deferred.
  They are deferred because they include external side effects, upload, write,
  timer, or automation execution risk. They are daily business-sensitive route
  families, so fallback must remain until a later PR proves parity, checker,
  smoke, rollback, and owner approval for each specific family.

## Phase 3F Shell/Navigation Spike

`/admin/customers` is a shell/navigation hardening spike that reuses the
Phase 3C `ListCustomersQuery` boundary for readonly customer list data loading.
It does not change the Phase 3A-D acceptance matrix, does not enter Phase 4
internal write scope, and does not mark the route as `delete_ready`.

The page fallback remains retained. The `frontend_compat` page layer only parses
request parameters, builds shell context, and renders the customer list
template; customer data loading and production fallback stay in the
`customer_read_model` application/use-case layer.
