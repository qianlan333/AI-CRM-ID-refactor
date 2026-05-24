# Phase 4G Profile Segment Template Companion Schema Plan

Status: Phase 4G schema planning only. This PR does not change runtime, implement a production repository, write migration, change DB schema, change `production_compat`, switch production owner, remove fallback, enable real external calls, mark `delete_ready`, or authorize production cutover.

## Scope

Planning scope: `/api/admin/automation-conversion/profile-segment-templates*`.

This includes future guardrails for profile segment template catalog/list/options/detail/create/update, but this PR does not add, delete, or modify any business route.

## Why Companion Schema Is Needed

Phase 4F confirmed that the legacy main data tables can support the profile segment template shape:

- `automation_profile_segment_template`
- `automation_profile_segment_category`
- `automation_profile_segment_option_mapping`

Phase 4F also confirmed the guardrail gaps:

- `template_code` duplicate protection is not idempotency. It can prevent one class of duplicate creates, but it cannot safely replay the same request and return the original response.
- Retry-safe create needs idempotency key storage scoped by route family, operation, operator, and idempotency key.
- Update replaces category and option mapping rows, so reliable rollback requires a before snapshot captured before child rows are deleted.
- `created_by` and `updated_by` are operator snapshots, not a complete audit trail.
- Dedicated audit event storage and before/after snapshot storage were not confirmed for this route family.

## Idempotency Schema Plan

Recommended strategy: new companion table, unless owners explicitly approve a shared request-log reuse before Phase 4H.

Proposed table: `automation_profile_segment_template_idempotency`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | yes | Primary key for diagnostics and retention cleanup. |
| `route_family` | `TEXT` | yes | Fixed to `/api/admin/automation-conversion/profile-segment-templates*`. |
| `operation` | `TEXT` | yes | `create` or `update`; create is the first robust idempotency requirement. |
| `operator` | `TEXT` | yes | Admin operator identity snapshot. |
| `idempotency_key` | `TEXT` | yes | Stable key from client or approved server source. |
| `request_hash` | `TEXT` | yes | Canonical hash of normalized payload. |
| `response_snapshot` | `JSONB` | yes | Stored original success or terminal response for replay. |
| `resource_type` | `TEXT` | yes | `profile_segment_template`. |
| `resource_id` | `BIGINT` | no | Template id once known. |
| `status` | `TEXT` | yes | `pending`, `succeeded`, `failed`, or `conflict`. |
| `created_at` | `TIMESTAMPTZ` | yes | Insert timestamp. |
| `updated_at` | `TIMESTAMPTZ` | yes | Last state transition timestamp. |

Unique constraint:

- `uq_profile_segment_template_idempotency_scope(route_family, operation, operator, idempotency_key)`

Indexes:

- `idx_profile_segment_template_idempotency_resource(resource_type, resource_id, created_at)`
- `idx_profile_segment_template_idempotency_status(status, updated_at)`

Conflict behavior: same key with a different `request_hash` returns a conflict and must not write main data.

Replay behavior: same key with the same `request_hash` returns `response_snapshot` and `resource_id` without creating another template.

Retention policy: keep at least 90 days or an owner-approved operational audit window. Cleanup is a later plan and must not be introduced by Phase 4G.

Rollback implication: idempotency rows provide replay evidence and resource id lookup, but rollback still depends on audit snapshots.

If owners choose to reuse an existing request log, Phase 4H must prove the existing table covers all required fields above. Otherwise, a new companion table remains the safer path.

## Audit / Rollback Schema Plan

Recommended strategy: new companion audit table, unless owners explicitly approve `admin_operation_logs` reuse and prove it can store full before/after snapshots and rollback payloads for this route family.

Proposed table: `automation_profile_segment_template_audit_log`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | yes | Primary key. |
| `route_family` | `TEXT` | yes | Profile segment template route family. |
| `operation` | `TEXT` | yes | `create`, `update`, `validation_failed`, `rollback`, or `replay`. |
| `operator` | `TEXT` | yes | Admin operator identity snapshot. |
| `resource_type` | `TEXT` | yes | `profile_segment_template`. |
| `resource_id` | `BIGINT` | no | Template id when known. |
| `before_snapshot` | `JSONB` | yes | Parent row, categories, and option mappings before update. |
| `after_snapshot` | `JSONB` | yes | Parent row, categories, and option mappings after create/update. |
| `request_payload` | `JSONB` | yes | Normalized request payload, excluding secrets. |
| `validation_result` | `JSONB` | yes | Validation success/failure and error contract. |
| `rollback_payload` | `JSONB` | yes | Compensating update payload or rollback instructions. |
| `side_effect_safety` | `JSONB` | yes | Evidence that no automation execution, send, WeCom, OpenClaw, MCP, timer, or workflow activation ran. |
| `created_at` | `TIMESTAMPTZ` | yes | Audit event timestamp. |

Indexes:

- `idx_profile_segment_template_audit_resource(resource_type, resource_id, created_at)`
- `idx_profile_segment_template_audit_operator(operator, created_at)`
- `idx_profile_segment_template_audit_operation(operation, created_at)`

Snapshot policy: update must capture the parent template, categories, and option mappings before deleting/reinserting child rows. Create must capture the created state after insert.

Rollback payload policy: create rollback can disable/revert the created template unless delete is separately approved. Update rollback must contain enough previous parent/category/mapping state to apply a compensating update.

Retention policy: keep at least 180 days or an owner-approved audit window. Any archival/deletion policy is a later, separately approved change.

## Explicit Non-Goals

This PR does not:

- change main data tables
- write migrations
- implement repository code
- dual-write production
- change legacy service behavior
- switch production route owner
- delete fallback
- narrow `production_compat`
- trigger WeCom, OpenClaw, MCP, timer, workflow execution, outbound send, or any external call

## Phase 4H Recommendation

Recommended next step: `companion_schema_migration_pr`.

Phase 4H should prepare migration readiness for companion idempotency/audit schema only, or stop at owner review if owners select `admin_operation_logs`/request-log reuse. It must not implement the production repository, switch production route owner, delete fallback, or mark `delete_ready`.
