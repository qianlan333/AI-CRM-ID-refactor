# Phase 4C Profile Segment Template Native Contract

Status: Phase 4C native contract implementation, pre-cutover.

This PR implements the Next native profile-segment-template bounded internal metadata contract for local, fixture, and staging-style validation. It does not perform production cutover, does not delete legacy fallback, does not narrow `production_compat`, does not change DB schema or migrations, does not change deploy configuration, does not enable real external calls, and does not mark `delete_ready`.

## Route Scope

Implemented in Next native contract for non-production/fixture/staging validation:

| Method | Route | Scope |
| --- | --- | --- |
| GET | `/api/admin/automation-conversion/profile-segment-templates/catalog` | catalog/read parity |
| GET | `/api/admin/automation-conversion/profile-segment-templates` | list parity |
| GET | `/api/admin/automation-conversion/profile-segment-templates/options` | options parity |
| GET | `/api/admin/automation-conversion/profile-segment-templates/{template_id}` | detail parity |
| POST | `/api/admin/automation-conversion/profile-segment-templates` | bounded internal metadata create |
| PUT | `/api/admin/automation-conversion/profile-segment-templates/{template_id}` | bounded internal metadata update |

Production ownership is unchanged. When the production facade is enabled, existing `production_compat` registration continues to retain the legacy fallback path. If a Next route is reached unexpectedly in production mode, the application contract must return degraded `production_unavailable` instead of fixture/local_contract/demo write success.

No DELETE route is implemented in Phase 4C.

## Business Continuity

The current automation operations configuration pages and APIs must continue to work through the existing production fallback. This PR keeps legacy fallback and `production_compat` intact. It only prepares a Next native contract that can be exercised outside production ownership.

Production data unavailable behavior is explicit: degraded/error, no fixture success. Rollback is revert of this PR because production fallback and route registration are retained.

## API Contract

List, options, catalog, and detail responses include:

- `ok`
- `source_status`
- `route_owner`
- `side_effect_safety`
- `items` / `templates` / `options` / `template`
- pagination or count fields where applicable

Create requires an idempotency key and validates a bounded metadata payload. Replaying the same idempotency key returns the same template result instead of creating duplicates. Duplicate name/code with a different idempotency key is rejected.

Update targets an explicit `template_id`, preserves unspecified fields, validates the submitted patch, returns 404 for missing templates, and emits rollback/audit evidence.

Supported metadata fields are intentionally bounded:

- `id` / `template_id`
- `name`
- `description`
- `segment_key` / `code`
- `conditions`
- `rules`
- `status`
- `sort_order`
- `created_at`
- `updated_at`

Validation rejects:

- missing create name
- name longer than 120 characters
- description longer than 1000 characters
- status outside `draft`, `active`, `inactive`
- non-JSON-object/list `rules` or `conditions`
- oversized `rules` or `conditions`
- dangerous side-effect fields

Audit and rollback evidence:

- create emits an audit event with operator, action, timestamp, and after snapshot
- create rollback identifies the created template and recommends status/field revert unless delete is separately approved
- update emits before/after snapshots and a rollback payload
- no external event dispatch is performed

## Side-Effect Exclusions

Phase 4C does not allow:

- run-due
- automation execution
- outbound send
- WeCom calls
- OpenClaw calls
- MCP real calls
- timer execution
- workflow activation
- customer pool state change
- media upload
- fallback removal

The `side_effect_safety` contract must keep real external/write runtime flags false, including real WeCom/OpenClaw/MCP/timer/outbound-send/workflow/customer-pool effects.

## Phase 4D Boundary

Phase 4D may plan a production repository or route ownership switch only after owner approval, parity, checker, smoke, rollback, and production config review. Production route ownership remains unchanged in Phase 4C.
