# Phase 4BD Tasks Fixture Native Implementation Owner Decision

## Summary

Phase 4BD pauses `/api/admin/automation-conversion/tasks*` before fixture/native runtime implementation. Phase 4BA through Phase 4BC completed metadata planning, schema/route confirmation, and fixture/native contract planning, but runtime implementation remains owner gated because tasks sit next to run-due, task execution, workflow execution, timer, and outbound-send behavior.

This package is docs/checker/test/state only. It does not implement runtime behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Integration fallback boundary:

- `aicrm_next.integration_gateway`

Current production owner:

- `production_compat` / `legacy_forward`

Paused route family:

- `/api/admin/automation-conversion/tasks*`

Next low-risk candidate:

- `/api/admin/automation-conversion/agents*`

## Business Continuity

本 PR 只生成 Phase 4BD tasks fixture/native implementation owner decision package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 run-due / task execution / workflow execution / timer / outbound send / agent-run / LLM generation / DeepSeek / OpenClaw / MCP / real external call，不影响当前自动化运营配置日常业务使用。tasks 与 agents 当前 production path 仍由 legacy fallback 保持。

## Business Value

Tasks are daily automation metadata, but their runtime surface is adjacent to execution and delivery behavior. Pausing at the owner-decision boundary preserves the completed planning artifacts without letting autopilot cross into execution risk. Selecting agents for metadata-only planning keeps Phase 4 moving while still excluding agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, and external calls.

## Completed Assets

- Phase 4BA tasks metadata planning.
- Phase 4BB tasks schema / route surface confirmation.
- Phase 4BC tasks fixture/native contract planning.

## Owner Decision Required

The owner must explicitly decide whether to:

- approve or decline tasks fixture/native runtime implementation;
- confirm list/create metadata-only scope;
- confirm detail/update/delete route expansion remains deferred;
- confirm run-due remains deferred;
- confirm task execution and workflow execution remain deferred;
- confirm timer and outbound send remain forbidden;
- confirm idempotency, audit, rollback, and dangerous-field rejection remain required;
- confirm rollback ownership before any runtime package.

## Safe Next Options

- Pause tasks and begin agents metadata-only planning.
- Approve a future tasks fixture/native runtime implementation package with explicit scope and rollback.
- Defer tasks until a separate execution boundary plan exists.

## Safety / Non-Goals

This PR does not:

- implement tasks runtime;
- implement run-due;
- execute tasks or workflows;
- enable timers or outbound send;
- implement agents runtime;
- implement agent-runs;
- enable LLM generation, DeepSeek, OpenClaw, MCP, WeCom, Payment, or OAuth calls;
- modify business routes;
- modify `production_compat`;
- modify schema or migrations;
- connect to staging or production data;
- write production;
- remove or narrow fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to docs, YAML, checker, tests, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4bd_tasks_fixture_native_implementation_owner_decision` because #660 completed Phase 4BC fixture/native contract planning and phase state requires owner approval before tasks runtime implementation.

## Next Action

Phase 4BE should begin `/api/admin/automation-conversion/agents*` metadata planning only. It must not implement runtime behavior, agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, real external calls, production owner switch, production write, or fallback removal.
