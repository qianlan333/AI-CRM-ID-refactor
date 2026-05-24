# Phase 4AP Task Groups Fixture Native Contract Plan

## Summary

Phase 4AP defines the fixture/local native contract for `/api/admin/automation-conversion/task-groups*`.

This is a planning package only. It does not implement runtime code, does not register a Next route, does not connect any database, and does not alter production traffic.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Route family:

- `/api/admin/automation-conversion/task-groups*`

Current production owner:

- `production_compat` / `legacy_forward`

The future fixture/native contract is limited to local list/create metadata behavior. Production remains legacy-forwarded.

## Business Continuity

本 PR 只生成 Phase 4AP task-groups fixture/native contract planning，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。task-groups 当前 production path 仍由 legacy fallback 保持。

## Business Value

Phase 4AO confirmed the legacy task-groups route and schema surface. Phase 4AP turns that evidence into a bounded fixture/local contract plan for the safest first slice: listing task groups and creating metadata-only groups. This reduces risk before any Next runtime implementation and keeps update/delete/archive and task execution paths separate.

## Planned Fixture Routes

Future fixture/local implementation may cover only:

- `GET /api/admin/automation-conversion/task-groups`
- `POST /api/admin/automation-conversion/task-groups`

Excluded from the first fixture/native contract:

- `PUT /api/admin/automation-conversion/task-groups/{group_id}`
- `DELETE /api/admin/automation-conversion/task-groups/{group_id}`
- `/api/admin/automation-conversion/tasks*`
- `tasks/run-due`
- task activate/pause/copy/preview-audience
- workflow execution
- timer execution
- outbound send
- real external calls

## Fixture Seed Contract

The fixture seed should contain deterministic metadata-only task groups:

- `phase4ap_default_group`
- `phase4ap_followup_group`

Required fields:

- `id`
- `program_id`
- `group_name`
- `sort_order`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`
- `archived_at`

The fixture must not include real customer data, external identifiers, send targets, workflow execution identifiers, or production-derived payloads.

## List Contract

Request:

- `program_id` query parameter.
- optional `include_archived` for fixture/local only.

Response:

- `ok`
- `source_status`
- `route_owner`
- `groups`
- `total`
- `count`
- `filters`
- `side_effect_safety`

Behavior:

- Default excludes archived groups.
- Sort by `sort_order ASC, id ASC`.
- Empty result is explicit fixture/local evidence, not production success.

## Create Contract

Request:

- `program_id` query parameter.
- `group_name` required.
- `sort_order` optional.
- `operator` / request-derived operator.
- `idempotency_key` required for future native create.

Response:

- `ok`
- `group`
- `audit_event`
- `rollback_payload`
- `idempotent_replay`
- `side_effect_safety`

Validation:

- Missing or blank `group_name` must fail.
- Duplicate `group_name` within the same `program_id` should fail in fixture/local.
- Dangerous fields must be rejected.

Dangerous fields:

- `run_due`
- `execute`
- `execution`
- `send`
- `wecom`
- `openclaw`
- `mcp`
- `timer`
- `workflow_activation`
- `customer_pool_state_change`
- `outbound_task`
- `agent_runtime_execution`
- `payment`
- `oauth`

## Idempotency, Audit, And Rollback

Future fixture/local create must include:

- idempotency scoped by route family, operation, operator, and idempotency key.
- same key plus same request hash replays the stored response.
- same key plus different request hash returns conflict.
- audit event with before snapshot `{}`, after snapshot, safe request payload, validation result, rollback payload, and side-effect safety.
- rollback payload sufficient to archive/remove the fixture-created group in local tests only.

## Side-Effect Safety

Every future fixture response must prove:

- real external call executed: false
- automation execution executed: false
- outbound send executed: false
- WeCom call executed: false
- OpenClaw call executed: false
- MCP call executed: false
- timer execution executed: false
- production data used: false

## Production Guard

If a future Next task-groups route is reached in production while fixture/local backend is active:

- POST must be blocked with degraded/unavailable semantics.
- Fixture/local success must not be returned as production success.
- Production route owner must remain legacy fallback until a separate owner-approved route switch.

## Risk / Rollback

Risk is limited to planning/checker/test/state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4ap_task_groups_fixture_native_contract_planning` because #646 completed Phase 4AO and the state file listed Phase 4AP as the only next allowed action. This package defines the fixture/native contract but does not implement it because runtime changes are outside the current low-risk autopilot scope.

## Next Action

Phase 4AQ should request owner confirmation for task-groups fixture/native implementation or generate an owner decision package. It must not change production owner, execute external calls, write production, remove fallback, or modify `production_compat`.
