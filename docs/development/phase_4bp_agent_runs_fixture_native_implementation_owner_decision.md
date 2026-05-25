# Phase 4BP Agent Runs Fixture Native Implementation Owner Decision

## Summary

Phase 4BP pauses `/api/admin/automation-conversion/agent-runs*` before fixture/native runtime implementation. Phase 4BM through Phase 4BO completed metadata planning, schema/route confirmation, and fixture/native contract planning, but runtime implementation remains owner gated because agent runs sit directly next to run creation, run execution, replay, orchestration, output generation, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer, and outbound-send behavior.

This package is docs/checker/test/state only. It does not implement runtime behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Integration fallback boundary:

- `aicrm_next.integration_gateway`

Current production owner:

- `production_compat` / `legacy_forward`

Paused route family:

- `/api/admin/automation-conversion/agent-runs*`

Next low-risk candidate:

- `/api/admin/automation-conversion/agent-replay`

## Business Continuity

This PR only generates a Phase 4BP agent-runs fixture/native implementation owner decision package. It does not connect to staging DB, does not connect to production data, does not execute staging smoke, does not write production, does not implement runtime, does not enable production repository as route owner, does not switch production route owner, does not delete legacy fallback, does not modify `production_compat`, does not enable run creation, run execution, replay, orchestration, output generation, LLM generation, DeepSeek, OpenClaw, MCP, workflow execution, timer, outbound send, or real external calls, and does not affect current automation conversion agent-run page/API daily use. Agent-runs and agent-replay current production paths remain legacy fallback.

## Business Value

Agent runs are execution-history metadata used for operational traceability, but crossing from contract planning into runtime implementation would touch run creation/execution and adjacent replay/orchestration surfaces. Pausing at the owner-decision boundary preserves the completed planning artifacts without letting autopilot cross into execution risk. Selecting agent-replay for metadata-only planning keeps Phase 4 moving while still excluding replay execution, run creation, run execution, orchestration, output generation, LLM generation, DeepSeek, OpenClaw/MCP, and external calls.

## Completed Assets

- Phase 4BM agent-runs metadata planning.
- Phase 4BN agent-runs schema / route surface confirmation.
- Phase 4BO agent-runs fixture/native contract planning.

## Owner Decision Required

The owner must explicitly decide whether to:

- approve or decline agent-runs fixture/native runtime implementation;
- confirm metadata list/detail-only scope;
- confirm run creation remains deferred;
- confirm run execution remains deferred;
- confirm replay and orchestration remain deferred;
- confirm agent output generation remains deferred;
- confirm LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer, and outbound send remain forbidden;
- confirm masked visibility and no production data remain required;
- confirm idempotency, audit, rollback, and dangerous-field rejection remain required;
- confirm rollback ownership before any runtime package.

## Safe Next Options

- Pause agent-runs and begin agent-replay metadata-only planning.
- Approve a future agent-runs fixture/native runtime implementation package with explicit scope and rollback.
- Defer agent-runs until a separate execution runtime boundary plan exists.

## Safety / Non-Goals

This PR does not:

- implement agent-runs runtime;
- create or execute runs;
- implement replay or orchestration;
- generate agent outputs;
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

Autopilot selected `phase_4bp_agent_runs_fixture_native_implementation_owner_decision` because #672 completed Phase 4BO fixture/native contract planning and phase state requires owner approval before agent-runs runtime implementation.

## Next Action

Phase 4BQ should begin `/api/admin/automation-conversion/agent-replay` metadata planning only. It must not implement runtime behavior, replay execution, run creation, run execution, orchestration, output generation, LLM generation, DeepSeek, OpenClaw/MCP, real external calls, production owner switch, production write, or fallback removal.
