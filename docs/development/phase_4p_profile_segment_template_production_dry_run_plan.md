# Phase 4P Profile Segment Template Production Dry-Run Plan

## Status

Phase 4P is production dry-run planning only.

- Production dry-run is not run by this PR.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No write canary.
- `delete_ready`: false.

This plan defines the future production dry-run scope, approvals, read-only and shadow strategies, data safety, evidence package, stop conditions, and Phase 4Q entry recommendation. It does not connect production data, invoke the Phase 4I SQLAlchemy adapter against production, execute the Phase 4O runner, or change any route owner.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Production dry-run / fallback boundary:

- `aicrm_next.integration_gateway`

Planning scope covers only:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

No business route is added, removed, or modified. Production facade enabled mode remains owned by legacy `production_compat` fallback. The SQLAlchemy adapter exists from Phase 4I but is not the production owner.

## Preconditions Before Future Production Dry-Run

All of these must be complete before any later PR can request a production dry-run:

- Phase 4O staging smoke evidence accepted by owners.
- automation_engine owner approval complete.
- integration_gateway owner approval complete.
- production config review complete.
- rollback owner assigned.
- DB/config owner assigned.
- Evidence storage path agreed.
- Legacy fallback validated.
- `production_compat` retained.
- No external side effects allowed.
- No route owner switch.

Fixture, local contract, demo, local test DB, and staging-only evidence cannot be treated as production parity success.

## Production Dry-Run Levels

| Level | Name | Authorized in Phase 4P | Writes | Production data access | Purpose |
| --- | --- | --- | --- | --- | --- |
| 0 | planning only | yes | no | no | Current Phase 4P. |
| 1 | production read-only parity dry-run | no | no | yes | Compare read payload shape and counts after config review. |
| 2 | production validation shadow | no | no | yes | Validate create/update payloads without writes. |
| 3 | production safe-namespace write dry-run | no | yes | yes | Future-only safe namespace write package after explicit approval. |
| 4 | production write canary | no | yes | yes | Explicitly outside Phase 4P and future-only. |

Phase 4P only authorizes Level 0 planning.

## Future Scope

Read-only candidates:

- catalog
- list
- options
- detail

Write shadow candidates:

- create validation only
- update validation only
- idempotency conflict simulation
- rollback payload generation

Explicitly forbidden in Phase 4P:

- real production create
- real production update
- route owner switch
- fallback removal
- production write canary
- external calls
- workflow activation
- automation execution
- customer pool state change

## Data Safety

Future production dry-run evidence must follow these data rules:

- Production DB URL secrets must be redacted.
- Reports must not contain secrets.
- Reports must not contain raw PII.
- Template payloads must be redacted or summarized.
- Audit/rollback evidence must be redacted.
- Any future write dry-run must use a separately approved safe namespace.
- Delete is not allowed unless separately approved.
- Fixture/local_contract/demo results must not be accepted as production success.

## Evidence Package

Future production dry-run evidence must include:

- Command.
- Config summary without secrets.
- Route owner unchanged evidence.
- `production_compat` retained evidence.
- Read parity summary.
- Validation shadow summary.
- Failed/skipped details.
- Side-effect safety summary.
- Fallback validation.
- Operator/timestamp.
- Owner signoff.

## Stop Conditions

Stop immediately if any of these conditions occur:

- Production config review incomplete.
- Owner approval missing.
- Fallback validation failed.
- `side_effect_safety` failed.
- External call detected.
- Route owner changed.
- `production_compat` changed.
- Unexpected write attempted.
- Secret redaction failed.

## Business Continuity

This PR only does Phase 4P production dry-run planning. It does not run production dry-run, does not connect production data, does not enable production repository, does not switch production route owner, does not remove legacy fallback, and does not modify `production_compat`. Current automation operations configuration pages and APIs remain unaffected.

Any future production dry-run, production repository enablement, route ownership switch, or production write canary must be handled in a separate PR after owner approval, checker, smoke, rollback, and production config review requirements are satisfied.

## Phase 4Q Recommendation

Recommended next step: production dry-run approval package.

Phase 4Q should package production dry-run approval and config review requirements. It must not run production dry-run and must not switch route owner.
