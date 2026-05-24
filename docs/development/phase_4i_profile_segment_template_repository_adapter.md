# Phase 4I Profile Segment Template Repository Adapter

## Status

Phase 4I implements a profile-segment-template production repository adapter behind an explicit backend flag. It does not switch production route ownership, does not perform production cutover, does not modify `production_compat`, does not remove legacy fallback, does not enable real external calls, and does not mark `delete_ready`.

Production facade enabled behavior remains unchanged: current production traffic for `/api/admin/automation-conversion/profile-segment-templates*` continues through legacy `production_compat` fallback. The adapter is only available when explicitly selected for repository/parity testing.

## Backend Flag

Default backend:

- `memory`
- fixture/in-memory repository remains the default for local and non-production contract tests

Opt-in backend:

- `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`
- fallback alias: `PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`

Database URL selection for the opt-in adapter:

- `AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL`
- `AICRM_NEXT_TEST_DATABASE_URL`
- shared settings `database_url`

Production guard:

- production mode with fixture backend returns degraded/blocked and must not produce fixture write success
- SQLAlchemy backend with an unavailable database returns production unavailable/degraded
- production route owner is not switched in this phase

## Repository Mapping

The adapter maps the Phase 4C Next contract onto existing legacy profile segment tables:

- `automation_profile_segment_template`
- `automation_profile_segment_category`
- `automation_profile_segment_option_mapping`

It also uses the Phase 4H companion tables:

- `automation_profile_segment_template_idempotency`
- `automation_profile_segment_template_audit_log`

Projection remains conservative:

- `template_name` maps to `name`
- `template_code` maps to `segment_key` / `code`
- `enabled` maps to `active` / `inactive`; draft parity still requires owner review
- category rows map to `rules.categories`
- option mappings map to category `option_mappings`

## Idempotency

Create requires an idempotency key.

- Same `route_family + operation + operator + idempotency_key` and same request hash replays the stored response snapshot.
- Same key with a different request hash returns idempotency conflict.
- Duplicate template name/code with a different idempotency key is rejected.
- The idempotency row is written and updated in the same transaction as the template create.

## Audit

Create/update writes an audit event to `automation_profile_segment_template_audit_log`.

Audit evidence includes:

- route family
- operation
- operator
- resource type/id
- before snapshot
- after snapshot
- request payload
- validation result
- rollback payload
- side effect safety

No external event dispatch is performed.

## Rollback

Create returns a rollback payload that identifies the created template and a compensating status/field revert strategy. Delete remains unapproved.

Update returns a rollback payload containing before/after snapshots. Because optimistic locking is not enforced in Phase 4I, the adapter reports a warning and leaves full stale-update policy to a later owner-approved phase.

## Validation

Validation continues to use the Phase 4C profile segment template contract:

- required create name
- bounded name/description length
- allowed status values
- JSON object/list rules and conditions
- dangerous side-effect fields rejected

## Parity Limitations

Phase 4I does not claim full production parity or production approval. Remaining parity work includes:

- draft/enabled owner mapping confirmation
- catalog/options payload parity against legacy controller responses
- production smoke planning
- production config review
- route ownership switch plan

## Business Continuity

Current automation operations production paths remain on legacy fallback. The adapter is not active for production traffic by default. Rollback is revert this PR or disable the backend flag. Any future production enablement requires feature flag, parity, checker, smoke, rollback, owner approval, and production config review.

## Phase 4J Conditions

Phase 4J should focus on repository parity and smoke planning. It must not directly switch production route owner, remove fallback, narrow `production_compat`, or enable external side effects.
