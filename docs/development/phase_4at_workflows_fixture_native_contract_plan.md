# Phase 4AT Workflows Fixture Native Contract Plan

## Summary

Phase 4AT plans the fixture/local native contract for `/api/admin/automation-conversion/workflows*` after Phase 4AS confirmed the legacy route and schema surface.

This package is planning-only. It defines a future fixture/local list/create metadata contract, deterministic seed requirements, idempotency, audit, rollback, and side-effect safety expectations. It does not implement runtime behavior or change production traffic.

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

本 PR 只生成 Phase 4AT workflows fixture/native contract planning package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / timer / outbound send，不影响当前自动化运营配置日常业务使用。workflows 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflow metadata drives automation configuration, but activation, timer execution, workflow nodes, and outbound send are high-risk paths. This contract plan defines a narrow fixture/local metadata boundary before any runtime work, so future implementation can validate list/create behavior without crossing into execution behavior.

## Planned Fixture Routes

Future fixture/local contract planning is limited to:

- `GET /api/admin/automation-conversion/workflows`
- `POST /api/admin/automation-conversion/workflows`

The wildcard route remains legacy-forwarded in production. Detail/update/delete, workflow nodes, run-due, execution records, timers, and outbound send remain deferred.

## Fixture Seed

Future fixture data must be deterministic and non-production:

- `phase4at_default_workflow`
- `phase4at_followup_workflow`

Required fields:

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

## List Contract

List may support:

- `program_id`
- `status`
- `include_archived`

Response must include:

- `ok`
- `source_status`
- `route_owner`
- `workflows`
- `total`
- `count`
- `filters`
- `side_effect_safety`

Archived workflows are excluded by default. Ordering is `updated_at_desc_id_desc`.

## Create Contract

Create requires:

- `workflow_name`
- `idempotency_key`

Create may accept:

- `workflow_code`
- `description`
- `program_id`
- `operator`

Create must reject:

- missing name;
- duplicate workflow code;
- invalid status;
- dangerous fields such as activation, node runtime, timer, send, execution, production owner, fallback, and external-call flags.

Create response must include:

- `ok`
- `workflow`
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
- create workflow nodes;
- execute workflows;
- enable timers;
- send outbound messages;
- remove fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to documentation, checker, test, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4at_workflows_fixture_native_contract_planning` because #650 completed workflows schema / route surface confirmation and phase state marked fixture/native contract planning as the next allowed low-risk package.

## Next Action

Phase 4AU must be a workflows fixture/native implementation owner decision package. Runtime implementation is not authorized in this PR and must not start without explicit owner confirmation.
