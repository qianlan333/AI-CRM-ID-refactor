# Phase 3D Recent Messages Readonly Hardening

Phase 3D only hardens this customer/archive readonly route:

- `GET /api/messages/{external_userid}/recent`

This PR does not change production route registration, remove fallback, delete
`production_compat`, enable real external calls, or touch write routes.

## Why This Route

This route is a readonly customer/archive surface with an existing Next exact
route and a clear legacy production fallback. It follows the same API boundary
hardening pattern as Phase 3A, Phase 3B, and Phase 3C.

It is handled after the pure customer list/detail/timeline routes because the
messages/archive route family has higher risk than simple customer read-model
reads. Phase 3D still does not enable real archive sync or any external calls.

## Business Continuity

Current customer recent-message reading must keep working during this hardening.
The change must not interrupt existing admin pages, customer APIs, sidebar,
customer profile, questionnaires, channels, payment, or automation paths.

The legacy production fallback remains in place. The `production_compat`
wildcard remains in place. No real archive sync, WeCom, Payment, OAuth,
OpenClaw, or MCP calls are enabled.

When production data is unavailable, the target route must return an explicit
degraded/error response instead of a `fixture`, `local_contract`, or `demo` fake
success payload. Rollback is to revert this PR; because fallback and route
behavior are preserved, rollback should not affect daily production usage.

## Replacement Boundary

The API layer owns request parsing and response serialization only.

The application/use-case layer owns the recent messages readonly orchestration.
It preserves production legacy facade fallback and maps unavailable production
data to degraded/error payloads.

`aicrm_next.integration_gateway` remains the legacy production fallback
transport boundary. Phase 3D does not move legacy facade calls into the target
API handler.

The archive adapter remains fake/contract guarded in this PR and does not
trigger real external calls. Write routes are out of scope.

## Delete Condition

This PR does not mark any fallback as delete-ready.

The corresponding legacy production fallback can only be considered for removal
after a separate PR proves:

- Next native production archive/read repository parity
- checker coverage
- production smoke coverage
- fallback and rollback conditions
- no fixture/local_contract/demo production success path

Until those conditions are met, fallback remains required.
