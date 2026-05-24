# Phase 4BF Agents Schema Route Surface Confirmation

Phase 4BF confirms the schema and route surface for `/api/admin/automation-conversion/agents*` before any fixture/native contract planning. This is a no-runtime-change autopilot work package.

## Summary

- Active candidate: `/api/admin/automation-conversion/agents*`.
- Capability owner: `aicrm_next.automation_engine`.
- Integration fallback boundary: `aicrm_next.integration_gateway`.
- Current production owner: `production_compat`.
- Current production behavior: `legacy_forward`.
- Legacy fallback retained: true.
- Fixture/local evidence is not production success.

## Confirmed Route Surface

The production compatibility layer currently forwards:

- `/api/admin/automation-conversion/agents`
- `/api/admin/automation-conversion/agents/{path:path}`

The legacy admin workspace and API surface referenced for future planning are:

- `GET /admin/automation-conversion/shared/agents`
- `POST /api/admin/automation-conversion/agents`
- `GET /api/admin/automation-conversion/agents/options`
- `GET /api/admin/automation-conversion/agents/{agent_code}`
- `POST /api/admin/automation-conversion/agents/{agent_code}/draft`
- `POST /api/admin/automation-conversion/agents/{agent_code}/publish`
- `DELETE /api/admin/automation-conversion/agents/{agent_code}`

Phase 4BF does not move any of these routes to Next ownership. It records the surface so Phase 4BG can plan a fixture/native contract for the first metadata-only subset.

## Confirmed Schema Surface

The bounded metadata table for the first native subset is `automation_agent_config`.

Read-model columns already referenced for admin projections:

- `id`
- `agent_code`
- `display_name`
- `scenario_code`
- `enabled`
- `updated_at`

Legacy metadata fields to preserve during future planning:

- `agent_code`
- `display_name`
- `description`
- `scenario_code`
- `enabled`
- `prompt_template_code`
- `tool_policy_code`
- `model_policy_code`

Related runtime tables are explicitly deferred:

- `automation_agent_run`
- `automation_agent_output`
- `automation_agent_llm_call_log`

## Native Boundary

The first native subset remains limited to:

- `list_agents_metadata`
- `create_agent_metadata_only`

Phase 4BG should plan fixtures/contracts for this subset only. It must include idempotency, audit placeholder, rollback, and dangerous-field rejection requirements before any runtime implementation is considered.

## Safety / Non-Goals

Phase 4BF does not:

- modify runtime code
- modify `production_compat`
- add, delete, or change business routes
- modify schema or migrations
- connect to staging or production data
- execute staging smoke
- write production
- enable a production repository route owner
- switch production route ownership
- delete or narrow legacy fallback
- execute agent runs
- generate with LLM/DeepSeek
- call OpenClaw/MCP
- trigger workflow execution
- trigger timers
- send outbound messages

## Deferred Surface

These are not in the first native subset and must stay separate:

- agent detail
- agent update
- agent delete
- agent draft/publish
- agent runs
- agent outputs
- agent replay
- agent orchestration
- LLM generation
- DeepSeek adapter
- OpenClaw/MCP call
- workflow execution
- timer execution
- outbound send

## Business Continuity

This PR only records Phase 4BF agents schema/route surface confirmation, updates static checkers/tests/state, and keeps the production path on legacy `production_compat` fallback. It does not affect the current automation conversion agents page/API daily use.

## Risk / Rollback

Risk is limited to docs/checker/test/state drift. Rollback is to remove the Phase 4BF docs/YAML/checker/test changes and restore `phase_execution_state.yaml` to the previous Phase 4BE state. Runtime behavior is unchanged.

## Phase 4BF Decision

Phase 4BF confirms the agents metadata route/schema surface and allows the next package to plan a fixture/native contract for metadata list/create only. Runtime implementation, production dry-run, production write, production repository route enablement, route ownership switch, fallback removal, real external calls, agent-run execution, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer execution, outbound send, canary approval, and delete readiness remain unauthorized.

## Next Action

Phase 4BG should create agents fixture/native contract planning for metadata list/create only. It must not implement runtime behavior, switch production owner, write production, execute external calls, remove fallback, or expand into agent runs/outputs/detail/update/delete/draft/publish.
