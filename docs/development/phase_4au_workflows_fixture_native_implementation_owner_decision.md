# Phase 4AU Workflows Fixture Native Implementation Owner Decision

## Summary

Phase 4AU pauses `/api/admin/automation-conversion/workflows*` before fixture/native runtime implementation. Phase 4AR through Phase 4AT completed metadata planning, schema/route confirmation, and fixture/native contract planning, but runtime implementation remains owner gated because workflows sit next to activation, nodes, execution, timer, and outbound-send behavior.

This package is docs/checker/test/state only. It does not implement runtime behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Integration fallback boundary:

- `aicrm_next.integration_gateway`

Current production owner:

- `production_compat` / `legacy_forward`

Paused route family:

- `/api/admin/automation-conversion/workflows*`

Next candidate recommendation:

- `/api/admin/automation-conversion/workflow-nodes*`

## Business Continuity

本 PR 只生成 Phase 4AU workflows fixture/native implementation owner decision package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / timer / outbound send，不影响当前自动化运营配置日常业务使用。workflows 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflows are a high-importance automation configuration surface. Pausing before runtime implementation prevents the autopilot from accidentally crossing into activation, execution, timer, or outbound-send behavior while still preserving the completed planning artifacts for later owner-approved work.

## Completed Assets

- Phase 4AR workflows metadata planning.
- Phase 4AS workflows schema / route surface confirmation.
- Phase 4AT workflows fixture/native contract planning.

## Owner Decision Required

The owner must explicitly decide whether to:

- approve or decline workflows fixture/native runtime implementation;
- confirm list/create metadata-only scope;
- confirm workflow activation remains deferred;
- confirm workflow nodes remain separate and deferred;
- confirm execution, timer, run-due, and outbound send remain forbidden;
- confirm idempotency, audit, rollback, and dangerous-field rejection remain required.

## Next Candidate

The next low-risk Phase 4 internal_write candidate is `/api/admin/automation-conversion/workflow-nodes*`, starting with metadata planning only.

This does not authorize workflow-node runtime implementation. The next package should only plan route surface, metadata boundaries, exclusions, idempotency/audit/rollback expectations, checker/test scope, and safe continuation criteria.

## Safety / Non-Goals

This PR does not:

- implement workflows runtime;
- implement workflow-node runtime;
- modify business routes;
- modify `production_compat`;
- modify schema or migrations;
- connect to staging or production data;
- write production;
- activate workflows;
- execute workflows;
- enable timers or run-due behavior;
- send outbound messages;
- remove or narrow fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to docs, YAML, checker, tests, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4au_workflows_fixture_native_implementation_owner_decision` because #651 completed Phase 4AT fixture/native contract planning and phase state requires owner approval before workflows runtime implementation.

## Next Action

Phase 4AV should begin `/api/admin/automation-conversion/workflow-nodes*` metadata planning only. It must not implement runtime behavior, execute workflows, enable timers, send outbound messages, change production owner, write production, or remove fallback.
