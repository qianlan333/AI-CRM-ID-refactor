# Phase 4AO Task Groups Schema And Route Surface Confirmation

## Summary

Phase 4AO confirms the legacy schema, route surface, response shape, and safety boundary for `/api/admin/automation-conversion/task-groups*`.

This is a planning/evidence package only. It does not implement a Next native route, repository, database adapter, production dry-run, route ownership switch, or fallback removal.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Route family:

- `/api/admin/automation-conversion/task-groups*`

Current production owner:

- `production_compat` / `legacy_forward`

Production behavior remains unchanged. The production route family is still forwarded through the legacy compatibility path.

## Business Continuity

本 PR 只生成 Phase 4AO task-groups schema / legacy route surface confirmation，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。task-groups 当前 production path 仍由 legacy fallback 保持。

## Business Value

Task-groups is the next Phase 4 internal_write candidate after action-templates was paused for staging owner/config decisions. Confirming the legacy route surface and schema first reduces migration risk before any native implementation work. The package identifies which parts are metadata-only and which parts must remain separate because they touch task execution, outbound send, or broader workflow behavior.

## Confirmed Production Ownership

Manifest and backlog both list `/api/admin/automation-conversion/task-groups*` as:

- capability owner: `aicrm_next.automation_engine`
- current runtime owner: `production_compat`
- production behavior: `legacy_forward`
- legacy fallback retained: true
- fixture allowed in production: false
- external side-effect risk: guarded
- replacement phase: `phase_4_internal_write`
- replacement category: `internal_write`

## Confirmed Route Surface

Production compatibility catch-all currently covers:

- `/api/admin/automation-conversion/task-groups`
- `/api/admin/automation-conversion/task-groups/{path:path}`
- all HTTP methods through the production compatibility router

The legacy route registration currently exposes:

- `GET /api/admin/automation-conversion/task-groups`
- `POST /api/admin/automation-conversion/task-groups`
- `PUT /api/admin/automation-conversion/task-groups/<group_id>`
- `DELETE /api/admin/automation-conversion/task-groups/<group_id>`

The first future Next native slice should stay metadata-only and start with list/create contract planning. Update/delete/archive behavior needs a separate approval because it changes grouping relationships for existing operation tasks.

## Confirmed Schema Surface

Main table:

- `automation_operation_task_group`

Columns:

- `id`
- `program_id`
- `group_name`
- `sort_order`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`
- `archived_at`

Index:

- `idx_automation_operation_task_group_program` on `(program_id, sort_order ASC, id ASC)`

Relationship:

- `automation_operation_task.group_id` references `automation_operation_task_group(id)` with `ON DELETE SET NULL`.

Delete behavior is archive-like in legacy code: the group row receives `archived_at`, and related operation tasks have `group_id` set to null. It is not a physical delete contract.

## Confirmed Request And Response Surface

List:

- Query: `program_id`
- Response: `{"ok": true, "groups": [...]}`
- Default ordering: `sort_order ASC, id ASC`
- Archived groups are excluded by default.

Create:

- Query: `program_id`
- Body: `group_name` required, `sort_order` optional
- Operator: request-derived operator id
- Success: HTTP 201 with `{"ok": true, "group": {...}}`
- Validation: missing `group_name` returns HTTP 400 with `{"ok": false, "error": "..."}`

Update:

- Path: `group_id`
- Body: `group_name` optional fallback to existing, `sort_order` optional fallback to existing
- Success: HTTP 200 with `{"ok": true, "group": {...}}`
- Missing group returns HTTP 404.
- Invalid empty name returns HTTP 400.

Delete/archive:

- Path: `group_id`
- Success: HTTP 200 with `{"ok": true, "deleted": true}`
- Missing group returns HTTP 404.
- Related operation tasks are ungrouped by setting `group_id` to null.
- This remains out of implementation scope for the next slice.

## Explicit Exclusions

The task-groups planning package excludes:

- `/api/admin/automation-conversion/tasks*`
- `/api/admin/automation-conversion/tasks/run-due`
- task activate/pause/copy/preview-audience
- workflow execution
- timer execution
- outbound send
- real WeCom / Payment / OAuth / OpenClaw / MCP calls
- production dry-run
- production write as route owner
- production owner switch
- fallback removal
- `production_compat` change

## Phase 4AP Recommendation

Phase 4AP should create task-groups fixture/native contract planning for a metadata-only list/create subset. It should not implement runtime behavior yet, and it must keep update/delete/archive separate unless explicitly approved.

## Risk / Rollback

Risk is limited to documentation/checker/test/state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4ao_task_groups_schema_route_surface_confirmation` because #645 completed Phase 4AN and the state file listed Phase 4AO as the only next allowed action. This package records route/schema evidence and advances the state to a future Phase 4AP fixture/native contract planning step.

## Next Action

Phase 4AP may do task-groups fixture/native contract planning for list/create metadata-only behavior. It must not change production owner, execute external calls, write production, remove fallback, or modify `production_compat`.
