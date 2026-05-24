# Phase 4AS Workflows Schema / Route Surface Confirmation

## Summary

Phase 4AS confirms the existing legacy route surface and PostgreSQL schema references for `/api/admin/automation-conversion/workflows*`.

This package is confirmation-only. It does not implement runtime behavior, does not execute workflows, does not connect to staging or production data, and does not change production traffic.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Current workflows production owner:

- `production_compat` / `legacy_forward`

Target route family:

- `/api/admin/automation-conversion/workflows*`

## Business Continuity

本 PR 只生成 Phase 4AS workflows schema / route surface confirmation package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / timer / outbound send，不影响当前自动化运营配置日常业务使用。workflows 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflows are core automation configuration metadata, but they sit next to execution, timer, node, and outbound-send behavior. This confirmation package documents the route and table boundary before any native contract planning so future work can stay metadata-only and avoid accidental execution side effects.

## Confirmed Route Surface

Production compatibility currently forwards:

- `GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD /api/admin/automation-conversion/workflows`
- `GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD /api/admin/automation-conversion/workflows/{path:path}`

The adjacent `/api/admin/automation-conversion/workflow-nodes*` family is explicitly deferred.

## Confirmed Schema Surface

Primary table:

- `automation_workflow`

Required metadata columns:

- `id`
- `program_id`
- `workflow_code`
- `workflow_name`
- `description`
- `review_status`
- `created_by_agent`
- `status`
- `segmentation_basis`
- `generation_mode`
- `profile_segment_template_id`
- `behavior_tier_scheme`
- `fallback_to_standard_content`
- `enabled`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

Confirmed indexes:

- `idx_automation_workflow_status`
- `idx_automation_workflow_program`
- `idx_automation_workflow_enabled`
- `idx_automation_workflow_review`

Deferred related tables:

- `automation_workflow_node`
- `automation_workflow_node_content`
- `automation_workflow_node_content_variant`
- `automation_workflow_audience`
- `automation_workflow_agent_binding`
- `automation_workflow_execution`
- `automation_workflow_execution_item`
- `automation_workflow_goal`
- `automation_workflow_node_transition`

## Metadata-Only Boundary

Future workflows native contract planning may cover list/create metadata behavior only after this confirmation. It must keep workflow activation, node runtime, run-due, timer execution, outbound send, and execution records out of scope.

## Safety / Non-Goals

This PR does not:

- implement Next runtime;
- add or remove routes;
- modify `production_compat`;
- modify schema or migrations;
- connect to staging or production data;
- write production;
- execute workflows;
- enable timers;
- send outbound messages;
- remove fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to documentation, checker, test, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4as_workflows_schema_route_surface_confirmation` because #649 completed workflows metadata planning and phase state marked schema / route surface confirmation as the next allowed low-risk package.

## Next Action

Phase 4AT may do workflows fixture/native contract planning for a metadata-only subset. It must not implement runtime behavior, execute workflows, enable timers, send outbound messages, write production, change production owner, remove fallback, or modify `production_compat`.
