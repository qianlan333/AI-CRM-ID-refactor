# Phase 3B Customer Profile Readonly Hardening

Phase 3B only hardens these two readonly customer profile route families:

- `GET /api/admin/customers/profile`
- `GET /api/admin/customers/profile/tags`

This PR does not change production route registration, remove fallback, delete
`production_compat`, enable real external calls, or touch write routes.

## Why These Routes

The Phase 2 backlog marks both routes as:

- `P0`
- `phase_3_readonly`
- `readonly`
- `external_side_effect_risk: none`

Both routes already have Next exact readonly owners, existing checker coverage,
and a clear legacy production fallback path. They are in the same customer
profile and sidebar capability cluster as the Phase 3A sidebar readonly
hardening, so they are the next low-risk readonly boundary to tighten before any
write, Payment, OAuth, WeCom, timer, or automation execution replacement work.

## Business Continuity

Current WeCom sidebar and customer profile daily usage must keep working during
this hardening. The change must not interrupt existing admin pages, customer
profile APIs, sidebar, questionnaires, channels, payment, or automation paths.

The legacy production fallback remains in place. The `production_compat`
wildcard remains in place. No real WeCom, Payment, OAuth, OpenClaw, or MCP calls
are enabled.

When production data is unavailable, the target routes must return an explicit
degraded/error response instead of a `fixture`, `local_contract`, or `demo` fake
success payload. Rollback is to revert this PR; because fallback and route
behavior are preserved, rollback should not affect daily production usage.

## Replacement Boundary

The API layer owns request parsing and response serialization only.

The application/use-case layer owns the customer profile and profile tags
readonly orchestration. It normalizes lookup inputs, calls the existing customer
context query, preserves production legacy facade fallback, and maps unavailable
production data to degraded/error payloads.

`aicrm_next.integration_gateway` remains the legacy production fallback
transport boundary. Phase 3B does not move legacy facade calls into the target
API handlers.

Write routes are out of scope. This spike does not replace
`/api/admin/customers/profile*` write or wildcard fallback paths, `/api/sidebar`
write/guarded routes, Payment, OAuth, WeCom callback, timer, or automation
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
