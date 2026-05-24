# Phase 3F Admin Customers Shell Hardening

Status: readonly shell/navigation hardening spike only. This document does not
change runtime behavior, delete fallback, narrow `production_compat`, enable
real external calls, or mark `/admin/customers` as `delete_ready`.

## Scope

This PR only covers:

- `GET /admin/customers`

It does not cover `/admin`, `/admin/customers/{external_userid}`, write routes,
Payment, OAuth, WeCom, timer, automation execution, archive sync, deploy
configuration, or production route registration.

## Why This Route

`/admin/customers` is listed in the Phase 3 acceptance report as a low-risk
shell/navigation candidate. It is a daily customer operations entry point, but
the page itself is a readonly shell and has no direct external side effect in
this spike.

Phase 3C already hardened the `/api/customers` readonly API boundary. This
spike reuses the same `ListCustomersQuery` application/use-case boundary for
the admin customer list page instead of letting the page handler choose the
legacy production facade directly.

## Business Continuity

The current backend customer list page must remain available for daily use. The
legacy production fallback remains retained through the customer read-model
application layer. The `production_compat` wildcard remains retained. No real
WeCom, Payment, OAuth, OpenClaw, MCP, archive sync, timer, or automation
execution calls are enabled.

When production data is unavailable, `/admin/customers` must render a degraded
page with `page_error`, an empty customer list, and total `0`. It must not show
`fixture`, `local_contract`, or `demo` customers as production success data.
Rollback is to revert this PR; because route registration and fallback are
retained, rollback should not affect current customer list usage.

## Replacement Boundary

The `frontend_compat` page layer only parses request parameters, builds shell
context, and renders `admin_console/customers.html`.

The `customer_read_model` application/use-case layer owns customer list data
loading and production fallback orchestration through `ListCustomersQuery`.

`aicrm_next.integration_gateway` remains the legacy production fallback
transport boundary. This PR does not move legacy facade calls into the
`/admin/customers` handler and does not touch write routes or detail page
routes.

## Delete Condition

This PR does not mark any fallback as delete-ready.

The corresponding legacy production fallback can only be considered for removal
after a separate PR proves:

- Next native production read repository parity
- page parity
- checker coverage
- browser smoke coverage
- fallback and rollback conditions
- owner approval
- no fixture/local_contract/demo production success path

Until those conditions are met, fallback remains required.
