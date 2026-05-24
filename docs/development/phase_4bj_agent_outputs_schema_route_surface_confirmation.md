# Phase 4BJ Agent Outputs Schema Route Surface Confirmation

Phase 4BJ confirms the schema and route surface for `/api/admin/automation-conversion/agent-outputs*` before any fixture/native contract planning. This is a no-runtime-change autopilot work package.

## Summary

- Active candidate: `/api/admin/automation-conversion/agent-outputs*`.
- Capability owner: `aicrm_next.automation_engine`.
- Integration fallback boundary: `aicrm_next.integration_gateway`.
- Current production owner: `production_compat`.
- Current production behavior: `legacy_forward`.
- Legacy fallback retained: true.
- Fixture/local evidence is not production success.

## Confirmed Route Surface

The production compatibility layer currently forwards:

- `/api/admin/automation-conversion/agent-outputs`
- `/api/admin/automation-conversion/agent-outputs/{path:path}`

The legacy API surface referenced for future planning is:

- `GET /api/admin/automation-conversion/agent-outputs`
- `GET /api/admin/automation-conversion/agent-outputs/{output_id}`
- `POST /api/admin/automation-conversion/agent-outputs/export`
- `GET /api/admin/automation-conversion/agent-outputs/export/{job_id}`

Phase 4BJ does not move any of these routes to Next ownership. It records the surface so Phase 4BK can plan a fixture/native contract for the first read-only metadata subset.

## Confirmed Schema Surface

The bounded metadata table for the first native subset is `automation_agent_output`.

Read-model columns already referenced for admin projections:

- `id`
- `output_id`
- `run_id`
- `request_id`
- `userid`
- `external_contact_id`
- `agent_code`
- `output_type`
- `rendered_output_text`
- `target_agent_code`
- `target_pool`
- `confidence`
- `reason`
- `need_human_review`
- `applied_status`
- `applied_at`
- `outcome_status`
- `outcome_value`
- `revision_of_output_id`
- `error_code`
- `error_message`
- `created_at`

Related runtime/export tables are explicitly deferred:

- `automation_agent_run`
- `automation_agent_output_export_job`
- `automation_agent_llm_call_log`

## Native Boundary

The first native subset remains limited to:

- `list_agent_outputs_metadata`
- `get_agent_output_metadata_detail`

Phase 4BK should plan fixtures/contracts for this subset only. It must include pagination, filters, masked/console visibility, not-found behavior, and no side-effect guarantees before any runtime implementation is considered.

## Deferred Surface

These are not in the first native subset and must stay separate:

- export job creation
- export job status lookup
- file download
- agent-runs
- agent replay
- agent orchestration
- LLM generation
- DeepSeek adapter
- OpenClaw/MCP call
- workflow execution
- timer execution
- outbound send

## Safety / Non-Goals

Phase 4BJ does not:

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
- create export jobs
- download files
- execute agent runs
- generate with LLM/DeepSeek
- call OpenClaw/MCP
- trigger workflow execution
- trigger timers
- send outbound messages

## Business Continuity

This PR only records Phase 4BJ agent-outputs schema/route surface confirmation, updates static checkers/tests/state, and keeps the production path on legacy `production_compat` fallback. It does not affect the current automation conversion agent-outputs page/API daily use.

## Business Value

Agent outputs support review and audit workflows, but the same route family also contains export/download and execution-adjacent surfaces. Confirming the schema/route boundary lets the next package plan safe read-only fixtures while keeping higher-risk export, download, run, generation, and external-call work separate.

## Risk / Rollback

Risk is limited to docs/checker/test/state drift. Rollback is to remove the Phase 4BJ docs/YAML/checker/test changes and restore `phase_execution_state.yaml` to the previous Phase 4BI state. Runtime behavior is unchanged.

## Autopilot Decision

Phase 4BJ confirms the agent-outputs metadata route/schema surface and allows the next package to plan a fixture/native contract for metadata list/detail only. Runtime implementation, production dry-run, production write, production repository route enablement, route ownership switch, fallback removal, real external calls, export job creation, file download, agent-run execution, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer execution, outbound send, canary approval, and delete readiness remain unauthorized.

## Next Action

Phase 4BK should create agent-outputs fixture/native contract planning for metadata list/detail only. It must not implement runtime behavior, create export jobs, download files, switch production owner, write production, execute external calls, remove fallback, or expand into agent-runs/replay/orchestration/generation.
