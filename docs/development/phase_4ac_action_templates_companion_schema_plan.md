# Phase 4AC Action Templates Companion Schema Plan

## Status

Phase 4AC is companion idempotency / audit schema planning only for `/api/admin/automation-conversion/action-templates*`.

- Phase 4AC companion schema planning only.
- No runtime change.
- No migration artifact.
- No production repository.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- No outbound send.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not add, remove, or modify business routes.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Schema/fallback boundary:

- `aicrm_next.integration_gateway`

Route family under planning:

- `/api/admin/automation-conversion/action-templates*`

Main legacy table:

- `automation_operation_templates`

## Why Companion Schema Is Needed

Phase 4AB confirmed `automation_operation_templates` as the action-template main table and confirmed the list/create surfaces, but it also confirmed the idempotency/audit gap.

The companion schema is needed because:

- `template_code` duplicate protection is not idempotency. It prevents duplicate codes, but it does not preserve retry semantics for the same operator/request.
- Retry-safe create needs idempotency key storage scoped by route family, operation, operator, and key.
- Create/update rollback needs before/after snapshots or response snapshots.
- `created_by` and `updated_by` are only operator snapshots, not a full audit trail.
- `automation_operation_templates` currently has no confirmed dedicated idempotency or audit storage.
- Future production repository enablement or route-owner switch must wait until idempotency, audit, and rollback foundations exist.

## Idempotency Schema Plan

Proposed companion table:

- `automation_operation_template_idempotency`

Planned fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | bigserial | yes | primary key |
| `route_family` | text | yes | fixed route-family scope |
| `operation` | text | yes | create or future confirmed metadata operation |
| `operator` | text | yes | operator identity for idempotency scope |
| `idempotency_key` | text | yes | caller-supplied retry key |
| `request_hash` | text | yes | normalized request hash |
| `response_snapshot` | jsonb | yes | redacted response snapshot for replay |
| `resource_type` | text | yes | `action_template` |
| `resource_id` | bigint | no | created action-template id when available |
| `status` | text | yes | `in_progress`, `completed`, `failed`, or `conflict` |
| `created_at` | timestamptz | yes | creation timestamp |
| `updated_at` | timestamptz | yes | latest state timestamp |

Unique constraint:

- `route_family + operation + operator + idempotency_key`

Indexes:

- `resource_type, resource_id, created_at`
- `status, updated_at`

Replay behavior:

- Same idempotency key and same request hash returns the stored redacted response snapshot.
- The write must not run again during replay.

Conflict behavior:

- Same idempotency key with a different request hash is a conflict.
- The service must reject the request and must not create or mutate an action template.

Retention policy:

- Retain long enough for operator retry windows and rollback review.
- Archive or purge only under separately approved retention policy.

Rollback implications:

- Idempotency records preserve the response/resource identity needed to understand whether a retry created a resource.
- They do not perform rollback by themselves; rollback still depends on audit payloads and later approved operational handling.

External side effects:

- None. The schema is for internal metadata create safety only.

## Audit / Rollback Schema Plan

Proposed companion table:

- `automation_operation_template_audit_log`

Planned fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | bigserial | yes | primary key |
| `route_family` | text | yes | fixed route-family scope |
| `operation` | text | yes | create or future confirmed metadata operation |
| `operator` | text | yes | operator identity |
| `resource_type` | text | yes | `action_template` |
| `resource_id` | bigint | no | target action-template id when available |
| `before_snapshot` | jsonb | yes | `{}` for create; redacted previous state for future update |
| `after_snapshot` | jsonb | yes | redacted resulting state |
| `request_payload` | jsonb | yes | redacted normalized request payload |
| `validation_result` | jsonb | yes | validation summary |
| `rollback_payload` | jsonb | yes | bounded rollback payload |
| `side_effect_safety` | jsonb | yes | evidence that no external side effects occurred |
| `created_at` | timestamptz | yes | audit timestamp |

Indexes:

- `resource_type, resource_id, created_at`
- `operator, created_at`
- `operation, created_at`

Snapshot policy:

- Store redacted metadata snapshots only.
- Do not store secrets, raw PII, raw external payloads, or LLM generation internals.
- For create, `before_snapshot` should be `{}` and `after_snapshot` should include the created metadata shape.
- For future update, only after route confirmation, store redacted before/after metadata.

Rollback payload policy:

- For create, identify the created action template and safe archive/delete strategy for a later approved phase.
- For future update, include enough previous state to restore metadata if update route is confirmed.
- Do not include production secrets, external call payloads, or raw PII.

Retention policy:

- Retain for rollback and owner review.
- Purge/archive only under separately approved retention policy.

External side effects:

- None. The audit plan records safety evidence; it does not trigger workflows, sends, timers, or integrations.

## Scope Constraints

Phase 4AC schema planning only supports:

- Future list/read parity.
- Future create CRM-local action template metadata.
- Future update only if an action-template update route is later confirmed.

Explicitly excluded:

- Generate route.
- From-workflow route.
- DeepSeek / LLM adapter.
- Workflow execution.
- Outbound send.
- Timer.
- OpenClaw / MCP.
- WeCom external call.
- Payment / OAuth.
- Customer pool state changes.
- Production route-owner switch.
- Fallback removal.
- `production_compat` narrowing.

## Migration Readiness

This PR does not write a migration.

Phase 4AD may prepare migration artifact/readiness only if owner explicitly confirms that direction. Any later migration must be:

- Additive-only.
- Companion-table only.
- No mutation of `automation_operation_templates`.
- No backfill.
- No destructive SQL.
- Separately approved for deployment by owner/release/config stakeholders.

Migration deployment must be a separate PR and approval step. Phase 4AC does not authorize migration execution.

## Business Continuity

本 PR 只生成 Phase 4AC action-templates companion idempotency/audit schema planning，不连接生产数据，不写生产，不实现 runtime，不写 migration，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。

## Risk / Rollback

Rollback is deleting the Phase 4AC document, YAML, checker, and test, plus any narrow Phase 4AB checker allowlist maintenance. Runtime behavior, production data, route ownership, fallback behavior, `production_compat`, schema, migrations, and production repositories are unchanged.

## Phase 4AD Recommendation

Recommended next step:

- `companion_schema_migration_readiness`

Phase 4AD may prepare additive-only companion schema migration artifact/readiness. It must not implement runtime, switch production owner, enable external calls, execute production writes, remove fallback, or modify `production_compat`.
