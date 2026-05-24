# Phase 4BH Agents Fixture Native Implementation Owner Decision

## Summary

Phase 4BH pauses `/api/admin/automation-conversion/agents*` before fixture/native runtime implementation. Phase 4BE through Phase 4BG completed metadata planning, schema/route confirmation, and fixture/native contract planning, but runtime implementation remains owner gated because agents sit next to agent-runs, outputs, draft/publish/delete, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer, and outbound-send behavior.

This package is docs/checker/test/state only. It does not implement runtime behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Integration fallback boundary:

- `aicrm_next.integration_gateway`

Current production owner:

- `production_compat` / `legacy_forward`

Paused route family:

- `/api/admin/automation-conversion/agents*`

Next low-risk candidate:

- `/api/admin/automation-conversion/agent-outputs*`

## Business Continuity

This PR only generates a Phase 4BH agents fixture/native implementation owner decision package. It does not connect to staging DB, does not connect to production data, does not execute staging smoke, does not write production, does not implement runtime, does not enable production repository as route owner, does not switch production route owner, does not delete legacy fallback, does not modify `production_compat`, does not enable agent-runs, agent outputs expansion, LLM generation, DeepSeek, OpenClaw, MCP, workflow execution, timer, outbound send, or real external calls, and does not affect current automation conversion agents page/API daily use. Agents and agent-outputs current production paths remain legacy fallback.

## Business Value

Agents are daily automation metadata, but their runtime surface is adjacent to model execution and delivery behavior. Pausing at the owner-decision boundary preserves the completed planning artifacts without letting autopilot cross into execution risk. Selecting agent-outputs for metadata-only planning keeps Phase 4 moving while still excluding export job creation, file download, agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, and external calls.

## Completed Assets

- Phase 4BE agents metadata planning.
- Phase 4BF agents schema / route surface confirmation.
- Phase 4BG agents fixture/native contract planning.

## Owner Decision Required

The owner must explicitly decide whether to:

- approve or decline agents fixture/native runtime implementation;
- confirm metadata list/create-only scope;
- confirm detail/draft/publish/delete route expansion remains deferred;
- confirm agent-runs remain deferred;
- confirm agent-outputs expansion remains deferred;
- confirm LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer, and outbound send remain forbidden;
- confirm idempotency, audit, rollback, and dangerous-field rejection remain required;
- confirm rollback ownership before any runtime package.

## Safe Next Options

- Pause agents and begin agent-outputs metadata-only planning.
- Approve a future agents fixture/native runtime implementation package with explicit scope and rollback.
- Defer agents until a separate agent runtime boundary plan exists.

## Safety / Non-Goals

This PR does not:

- implement agents runtime;
- implement agent detail, draft, publish, or delete;
- implement agent-runs;
- expand agent outputs;
- enable LLM generation, DeepSeek, OpenClaw, MCP, WeCom, Payment, or OAuth calls;
- execute workflows;
- enable timers or outbound send;
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

Autopilot selected `phase_4bh_agents_fixture_native_implementation_owner_decision` because #664 completed Phase 4BG fixture/native contract planning and phase state requires owner approval before agents runtime implementation.

## Next Action

Phase 4BI should begin `/api/admin/automation-conversion/agent-outputs*` metadata planning only. It must not implement runtime behavior, export job creation, file download, agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, real external calls, production owner switch, production write, or fallback removal.
