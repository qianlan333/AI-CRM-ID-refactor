# Phase 4H Profile Segment Template Companion Migration

## Status

Phase 4H prepares a companion schema migration artifact for profile-segment-template idempotency and audit readiness. It is additive-only and does not change runtime behavior.

- No production repository implementation.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback remains retained.
- No real external calls.
- No DB backfill.
- `delete_ready`: false.

## Companion Tables

### `automation_profile_segment_template_idempotency`

Purpose: store future create/update idempotency evidence for `/api/admin/automation-conversion/profile-segment-templates*` without changing the existing profile segment main tables.

Fields:

| field | type | required | notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | yes | Primary key. |
| `route_family` | `TEXT` | yes | Bounded route family scope. |
| `operation` | `TEXT` | yes | Planned values: `create`, `update`, `validation_failed`, `rollback`, `replay`. |
| `operator` | `TEXT` | yes | Admin operator identity snapshot. |
| `idempotency_key` | `TEXT` | yes | Client or server supplied stable key. |
| `request_hash` | `TEXT` | yes | Canonical hash of normalized request payload. |
| `response_snapshot` | `JSONB` | yes | Stored terminal response for replay. |
| `resource_type` | `TEXT` | yes | Defaults to `profile_segment_template`. |
| `resource_id` | `BIGINT` | no | Template id once known. |
| `status` | `TEXT` | yes | Planned values: `pending`, `succeeded`, `failed`, `conflict`. |
| `created_at` | `TIMESTAMPTZ` | yes | Creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | yes | Last status transition timestamp. |

Constraints and indexes:

- Unique constraint: `(route_family, operation, operator, idempotency_key)`.
- Resource lookup index: `(resource_type, resource_id, created_at)`.
- Status lookup index: `(status, updated_at)`.

Retention assumption: keep records for at least the owner-approved operational replay window. Cleanup must be a later reviewed task.

Rollback note: before deployment, rollback is reverting this PR. After a future migration deployment, rollback must be handled by production config review with backup/smoke/rollback approval.

### `automation_profile_segment_template_audit_log`

Purpose: store future audit trail, before/after snapshots, rollback payload, and side-effect safety evidence for profile segment template internal metadata writes.

Fields:

| field | type | required | notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | yes | Primary key. |
| `route_family` | `TEXT` | yes | Bounded route family scope. |
| `operation` | `TEXT` | yes | Planned values: `create`, `update`, `validation_failed`, `rollback`, `replay`. |
| `operator` | `TEXT` | yes | Admin operator identity snapshot. |
| `resource_type` | `TEXT` | yes | Defaults to `profile_segment_template`. |
| `resource_id` | `BIGINT` | no | Template id when known. |
| `before_snapshot` | `JSONB` | yes | Parent template, category, and option mapping state before update. |
| `after_snapshot` | `JSONB` | yes | Parent template, category, and option mapping state after write. |
| `request_payload` | `JSONB` | yes | Normalized request payload, excluding secrets. |
| `validation_result` | `JSONB` | yes | Validation outcome and error contract. |
| `rollback_payload` | `JSONB` | yes | Compensating payload or rollback instructions. |
| `side_effect_safety` | `JSONB` | yes | Evidence that no run-due, execution, send, WeCom, OpenClaw, MCP, timer, workflow activation, or customer pool state change ran. |
| `created_at` | `TIMESTAMPTZ` | yes | Audit event timestamp. |

Indexes:

- Resource lookup: `(resource_type, resource_id, created_at)`.
- Operator lookup: `(operator, created_at)`.
- Operation lookup: `(operation, created_at)`.

Retention assumption: keep records for the owner-approved audit window. Archive/deletion policy is not part of Phase 4H.

Rollback note: this table only prepares storage. Future production repository usage must define data rollback and audit review before any route owner switch.

## Business Continuity

This phase does not affect current automation operations runtime. The artifact is schema readiness only: no current route behavior changes, no production repository usage, no production route owner switch, and no fallback narrowing. Future production migration deployment must include backup, smoke, rollback, production config review, and owner approval.

## Future Usage

Phase 4I may plan or implement a production repository adapter that uses these tables behind no route-owner switch. Route owner switch remains unauthorized. Legacy fallback remains required until parity, checker, smoke, rollback, owner approval, and production config review are complete.
