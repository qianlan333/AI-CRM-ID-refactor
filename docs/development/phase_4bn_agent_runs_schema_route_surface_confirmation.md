# Phase 4BN Agent Runs Schema Route Surface Confirmation

## Summary

Phase 4BN confirms the schema and route surface for the `/api/admin/automation-conversion/agent-runs*` metadata-only list/detail subset. This package follows Phase 4BM metadata planning and prepares Phase 4BO fixture/native contract planning without implementing runtime behavior.

This package is docs/tools/tests/state only. It does not execute or create agent runs.

## Architecture Boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback remains required.
- Fixture/local evidence is not production evidence.

## Confirmed Route Surface

Metadata-only surfaces for later contract planning:

- `GET /api/admin/automation-conversion/agent-runs`
- `GET /api/admin/automation-conversion/agent-runs/{run_id}`

Deferred surfaces:

- `POST /api/admin/automation-conversion/agent-runs`
- `POST /api/admin/automation-conversion/agent-runs/{run_id}/execute`
- `/api/admin/automation-conversion/agent-replay`
- `/api/admin/automation-conversion/agent-orchestration*`
- `/api/admin/automation-conversion/agent-outputs*` expansion

## Confirmed Schema Surface

The first native subset should read metadata from `automation_agent_run` only. The expected read model includes run identity, request reference, agent code, run status, trigger source, optional user/contact/task/workflow references, timestamps, duration/error metadata, output count, and metadata payload references.

Related output payloads, LLM logs, orchestration events, and workflow execution tables remain deferred.

## Business Continuity

Production continues to use the existing legacy-forwarded agent-run APIs. This PR does not connect to staging DB or production DB, does not execute staging smoke, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable run creation, run execution, replay, orchestration, output generation, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer execution, outbound send, or real external calls.

## Business Value

Confirming the route/schema surface turns the Phase 4BM metadata plan into concrete fixture/native contract inputs while preserving execution safety. It keeps the next package focused on local metadata list/detail fixtures instead of runtime behavior.

## Safety / Non-Goals

This PR does not:

- implement runtime behavior;
- create or execute agent runs;
- trigger replay or orchestration;
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

Autopilot selected `phase_4bn_agent_runs_schema_route_surface_confirmation` because #670 completed Phase 4BM metadata planning and phase state requires schema/route surface confirmation before fixture/native contract planning.

## Next Action

Phase 4BO should plan the agent-runs fixture/native contract for metadata list/detail only. It must not implement runtime behavior, create or execute runs, trigger replay/orchestration, generate outputs, enable LLM generation, call DeepSeek/OpenClaw/MCP, write production, switch production owner, remove fallback, or enable real external calls.
