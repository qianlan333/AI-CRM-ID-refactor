# Phase 4AY Workflow Nodes Fixture Native Implementation Owner Decision

## Summary

Phase 4AY pauses `/api/admin/automation-conversion/workflow-nodes*` before fixture/native runtime implementation. Phase 4AV through Phase 4AX completed metadata planning, schema/route confirmation, and fixture/native contract planning, but runtime implementation remains owner gated because workflow nodes sit next to transitions, workflow execution, timer, run-due, and outbound-send behavior.

This package is docs/checker/test/state only. It does not implement runtime behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Integration fallback boundary:

- `aicrm_next.integration_gateway`

Current production owner:

- `production_compat` / `legacy_forward`

Paused route family:

- `/api/admin/automation-conversion/workflow-nodes*`

## Business Continuity

本 PR 只生成 Phase 4AY workflow-nodes fixture/native implementation owner decision package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / node transition runtime / timer / outbound send，不影响当前自动化运营配置日常业务使用。workflow-nodes 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflow nodes are automation metadata that can shape future workflow behavior. Pausing before runtime implementation prevents the autopilot from crossing into transitions, execution, timer, or outbound-send behavior while preserving the completed planning artifacts for later owner-approved work.

## Completed Assets

- Phase 4AV workflow-nodes metadata planning.
- Phase 4AW workflow-nodes schema / route surface confirmation.
- Phase 4AX workflow-nodes fixture/native contract planning.

## Owner Decision Required

The owner must explicitly decide whether to:

- approve or decline workflow-nodes fixture/native runtime implementation;
- confirm list/create metadata-only scope;
- confirm detail/update/delete route expansion remains deferred;
- confirm node transition runtime remains deferred;
- confirm workflow execution, timer, run-due, and outbound send remain forbidden;
- confirm idempotency, audit, rollback, and dangerous-field rejection remain required;
- confirm rollback ownership before any runtime package.

## Safe Next Options

- Pause workflow-nodes and select the next low-risk Phase 4 internal_write candidate.
- Approve a future fixture/native runtime implementation package with explicit scope and rollback.
- Defer workflow-nodes until a separate transition/runtime plan exists.

## Safety / Non-Goals

This PR does not:

- implement workflow-node runtime;
- implement node transition runtime;
- modify business routes;
- modify `production_compat`;
- modify schema or migrations;
- connect to staging or production data;
- write production;
- execute workflows;
- enable timers or run-due behavior;
- send outbound messages;
- remove or narrow fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to docs, YAML, checker, tests, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision` because #655 completed Phase 4AX fixture/native contract planning and phase state requires owner approval before workflow-nodes runtime implementation.

## Next Action

Phase 4AZ should select the next low-risk Phase 4 internal_write candidate from backlog/manifest and begin with planning only. It must not implement runtime behavior, execute workflows, enable timers, send outbound messages, change production owner, write production, or remove fallback.
