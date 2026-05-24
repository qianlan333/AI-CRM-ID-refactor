# Phase 4AX Workflow Nodes Fixture Native Contract Plan

## Summary

Phase 4AX plans the fixture/local native contract for `/api/admin/automation-conversion/workflow-nodes*` after Phase 4AW confirmed the legacy route and schema surface.

This package is planning-only. It defines a future fixture/local list/create metadata contract, deterministic seed requirements, idempotency, audit, rollback, and side-effect safety expectations. It does not implement runtime behavior or change production traffic.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Current workflow-nodes production owner:

- `production_compat` / `legacy_forward`

Target route family:

- `/api/admin/automation-conversion/workflow-nodes*`

## Business Continuity

本 PR 只生成 Phase 4AX workflow-nodes fixture/native contract planning package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / timer / outbound send / node transition runtime，不影响当前自动化运营配置日常业务使用。workflow-nodes 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflow nodes define the operational sequence for automation workflows, so a careless migration can accidentally affect timing, transitions, or sends. This contract plan keeps the scope to fixture/local metadata list/create behavior and makes the high-risk runtime edges explicit before any implementation can start.

## Planned Fixture Routes

Future fixture/local contract planning is limited to:

- `GET /api/admin/automation-conversion/workflow-nodes`
- `POST /api/admin/automation-conversion/workflow-nodes`

The wildcard route remains legacy-forwarded in production. Detail/update/delete, workflow activation, transitions, run-due, execution records, timers, and outbound send remain deferred.

## Fixture Seed

Future fixture data must be deterministic and non-production:

- `phase4ax_welcome_node`
- `phase4ax_followup_node`

Required fields:

- `id`
- `workflow_id`
- `node_code`
- `node_name`
- `target_audience_code`
- `trigger_mode`
- `day_offset`
- `send_time`
- `timezone`
- `position_index`
- `enabled`
- `created_at`
- `updated_at`

## List Contract

List may support:

- `workflow_id`
- `target_audience_code`
- `enabled`

Response must include:

- `ok`
- `source_status`
- `route_owner`
- `workflow_nodes`
- `total`
- `count`
- `filters`
- `side_effect_safety`

Disabled nodes are included by default because fixture/local planning should reveal the full configured sequence. Ordering is `workflow_id_position_index_id_asc`.

## Create Contract

Create requires:

- `workflow_id`
- `node_name`
- `idempotency_key`

Create may accept:

- `node_code`
- `target_audience_code`
- `trigger_mode`
- `day_offset`
- `send_time`
- `timezone`
- `position_index`
- `operator`

Create must reject:

- missing workflow id;
- missing name;
- duplicate node code within a workflow;
- invalid target audience;
- invalid trigger mode;
- dangerous fields such as transition runtime, timer, send, execution, production owner, fallback, and external-call flags.

Create response must include:

- `ok`
- `workflow_node`
- `audit_event`
- `rollback_payload`
- `idempotent_replay`
- `side_effect_safety`

## Idempotency / Audit / Rollback

Future implementation must use route-family, operation, operator, and idempotency-key scope. Same payload replay must return idempotent replay; different payload with the same key must conflict.

Audit must include a create event, empty before snapshot, after snapshot, rollback payload, and side-effect-safety evidence.

## Safety / Non-Goals

This PR does not:

- implement Next runtime;
- add or remove routes;
- modify `production_compat`;
- modify schema or migrations;
- connect to staging or production data;
- write production;
- activate workflows;
- execute workflows;
- enable node transition runtime;
- enable timers;
- send outbound messages;
- remove fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to documentation, checker, test, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4ax_workflow_nodes_fixture_native_contract_planning` because #654 completed workflow-nodes schema / route surface confirmation and phase state marked fixture/native contract planning as the next allowed low-risk package.

## Next Action

Phase 4AY must be a workflow-nodes fixture/native implementation owner decision package. Runtime implementation is not authorized in this PR and must not start without explicit owner confirmation.
