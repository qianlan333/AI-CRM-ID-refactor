# Phase 4AD Action Templates Companion Migration

## Status

Phase 4AD prepares an additive-only companion schema migration artifact for `/api/admin/automation-conversion/action-templates*`.

- Phase 4AD companion schema migration artifact.
- Additive-only.
- No production repository.
- No runtime implementation.
- No route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No real external calls.
- No automation execution.
- No outbound send.
- `delete_ready`: false.

This PR adds schema artifacts for companion idempotency and audit storage only. It does not deploy the migration, connect to production data, or change any route behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Schema/fallback boundary:

- `aicrm_next.integration_gateway`

Route family:

- Future schema support only for `/api/admin/automation-conversion/action-templates*`

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not add, remove, or modify business routes.

## Migration Artifact

The artifact is represented in:

- `wecom_ability_service/schema_postgres.sql`
- `wecom_ability_service/db/migrations/postgres_migrations.py`

It creates two new companion tables without mutating `automation_operation_templates`.

## New Tables

### `automation_operation_template_idempotency`

Purpose:

- Stores retry-safe idempotency records for future bounded CRM-local action-template metadata create operations.
- A `template_code` uniqueness check is still not idempotency; replay needs route, operation, operator, key, request hash, and a redacted response snapshot.

Fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | yes | Primary key. |
| `route_family` | `TEXT` | yes | Route family scope. |
| `operation` | `TEXT` | yes | Future metadata operation, initially create. |
| `operator` | `TEXT` | yes | Operator identity used in idempotency scope. |
| `idempotency_key` | `TEXT` | yes | Caller-supplied retry key. |
| `request_hash` | `TEXT` | yes | Normalized request hash for replay conflict detection. |
| `response_snapshot` | `JSONB` | yes | Redacted response snapshot; default `{}`. |
| `resource_type` | `TEXT` | yes | Defaults to `action_template`. |
| `resource_id` | `BIGINT` | no | Future `automation_operation_templates.id` when available. |
| `status` | `TEXT` | yes | Documented values: `pending`, `succeeded`, `failed`, `conflict`. |
| `created_at` | `TIMESTAMPTZ` | yes | Creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | yes | Latest idempotency state timestamp. |

Constraint:

- `UNIQUE (route_family, operation, operator, idempotency_key)`

Indexes:

- `idx_action_template_idempotency_resource` on `resource_type, resource_id, created_at`
- `idx_action_template_idempotency_status` on `status, updated_at`

Retention assumptions:

- Retain long enough for operator retry windows and rollback review.
- Archive or purge only under a separately approved retention policy.

Rollback note:

- The table records replay and resource identity. It does not perform rollback by itself.

Deployment:

- Not authorized by this PR.

### `automation_operation_template_audit_log`

Purpose:

- Stores redacted audit and rollback evidence for future bounded CRM-local action-template metadata writes.
- `created_by` and `updated_by` remain operator snapshots on the main table; they are not a complete audit trail.

Fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | yes | Primary key. |
| `route_family` | `TEXT` | yes | Route family scope. |
| `operation` | `TEXT` | yes | Documented values include `create`, `validation_failed`, `rollback`, `replay`; `update` only if a route is later confirmed. |
| `operator` | `TEXT` | yes | Operator identity at action time. |
| `resource_type` | `TEXT` | yes | Defaults to `action_template`. |
| `resource_id` | `BIGINT` | no | Target action-template id when available. |
| `before_snapshot` | `JSONB` | yes | `{}` for create; redacted previous state for future update. |
| `after_snapshot` | `JSONB` | yes | Redacted resulting state. |
| `request_payload` | `JSONB` | yes | Redacted normalized request payload. |
| `validation_result` | `JSONB` | yes | Validation summary. |
| `rollback_payload` | `JSONB` | yes | Bounded rollback payload. |
| `side_effect_safety` | `JSONB` | yes | Evidence that no external call, execution, timer, or outbound send occurred. |
| `created_at` | `TIMESTAMPTZ` | yes | Audit timestamp. |

Indexes:

- `idx_action_template_audit_resource` on `resource_type, resource_id, created_at`
- `idx_action_template_audit_operator` on `operator, created_at`
- `idx_action_template_audit_operation` on `operation, created_at`

Retention assumptions:

- Retain for rollback and owner review.
- Purge/archive only under separately approved retention policy.

Rollback note:

- Rollback payloads are evidence for a future approved rollback process. This PR does not implement rollback execution.

Deployment:

- Not authorized by this PR.

## Business Continuity

本 PR 只新增 action-templates companion idempotency/audit schema migration artifact，不连接生产数据，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。migration 是否部署、何时部署、如何回滚必须另行通过 production config review 和 owner approval。

The current automation operations runtime and production path are unchanged. The schema artifact has no effect until a separately approved migration deployment occurs, and future deployment must include backup, smoke, rollback, and owner approval.

## Safety / Non-Goals

This PR does not:

- Implement runtime behavior.
- Implement a production repository adapter.
- Connect to production data.
- Deploy or run the migration.
- Backfill data.
- Mutate `automation_operation_templates`.
- Add triggers or runtime hooks.
- Enable external calls.
- Change route ownership.
- Remove fallback.
- Modify `production_compat`.

## Future Usage

Phase 4AE may plan or implement fixture/native contract behavior behind a local-only repository using this schema shape.

Phase 4AF or later may plan a repository adapter, after additional owner approval and safety checks.

Route owner switch is still not allowed. Legacy fallback remains required.

## Risk / Rollback

Risk is limited to additive schema artifact text. Runtime behavior is unchanged.

Rollback before deployment is reverting this PR. If a future migration deployment occurs, rollback must be separately approved with production config review, backup, smoke, and rollback owner confirmation.

## Phase 4AE Recommendation

Recommended next step:

- `action_templates_fixture_native_contract_behind_local_only_repository`

Phase 4AE can use the companion schema shape for fixture/native contract work. It must not switch production owner, enable external calls, remove fallback, or implement production repository behavior.
