# Phase 3A Sidebar Readonly Replacement Spike

Phase 3A only hardens the first two P0 readonly sidebar route families:

- `GET /api/sidebar/contact-binding-status`
- `GET /api/sidebar/customer-context`

This PR does not change production route registration, remove fallback, delete
`production_compat`, enable real external calls, or touch write routes.

## Why These Routes First

These two routes are the first replacement spike because the Phase 2 backlog
marks them as:

- `P0`
- `phase_3_readonly`
- `readonly`
- `external_side_effect_risk: none`

Both already have Next exact readonly routes, existing checker coverage, and a
clear legacy production fallback path. That makes them suitable for boundary
hardening before any write, Payment, OAuth, WeCom, timer, or automation execution
replacement work.

## Business Continuity

Current WeCom sidebar daily usage must keep working during this spike. The
replacement work must not interrupt sidebar pages, customer context, binding
status, customer profile links, questionnaires, channels, payment, or automation
paths.

The legacy production fallback remains in place. The `production_compat`
wildcard remains in place. No real WeCom, Payment, OAuth, OpenClaw, or MCP calls
are enabled.

When production data is unavailable, the target routes must return an explicit
degraded/error response instead of a `fixture`, `local_contract`, or `demo` fake
success payload. Rollback is to revert this PR; because fallback and route
behavior are preserved, rollback should not affect daily production usage.

## Replacement Boundary

The API layer owns request parsing and response serialization only.

The application/use-case layer owns orchestration for production fallback,
non-production fixture fallback, input normalization, and degraded/error
payloads.

`aicrm_next.integration_gateway` remains the legacy transport boundary. Phase 3A
keeps legacy customer reads behind application/use-case or adapter boundaries
and does not move legacy facade calls into the target API endpoints.

Write routes are out of scope. In particular, this spike does not replace
`/api/sidebar/bind-mobile`, `/api/sidebar/lead-pool/*`, `signup-tags`,
`marketing-status`, Payment, OAuth, WeCom callback, timer, or automation
execution routes.

## Delete Condition

This PR does not mark any fallback as delete-ready.

The corresponding legacy production fallback can only be considered for removal
after a separate PR proves:

- Next native production read repository parity
- checker coverage
- production smoke coverage
- fallback and rollback conditions
- no fixture/local_contract/demo production success path

Until those conditions are met, fallback remains required.
