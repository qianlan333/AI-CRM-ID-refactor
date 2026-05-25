# Phase 4BO Agent Runs Fixture Native Contract Planning

Phase 4BO plans a fixture/native contract for the first `/api/admin/automation-conversion/agent-runs*` read-only metadata subset. This is a no-runtime-change autopilot work package.

## Summary

- Active candidate: `/api/admin/automation-conversion/agent-runs*`.
- Planned subset: metadata list/detail only.
- Current production owner: `production_compat`.
- Current production behavior: `legacy_forward`.
- Legacy fallback retained: true.
- Fixture data remains local and deterministic.

This PR records the fixture seed, list/detail contract, visibility requirements, and side-effect safety boundary for a future implementation decision package. It does not implement a native runtime path.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- The production path remains legacy-forwarded through `production_compat`.
- Fixture data is not production data and must not be used as production evidence.

## Planned Fixture Routes

The fixture/native contract plan is limited to:

- `GET /api/admin/automation-conversion/agent-runs`
- `GET /api/admin/automation-conversion/agent-runs/{run_id}`

Both routes are read-only metadata surfaces. The plan requires deterministic fixture rows and read responses only.

## Fixture Seed

The fixture seed should include two deterministic agent run rows:

- `phase4bo_run_completed_metadata`
- `phase4bo_run_failed_metadata`

Required fields:

- `id`
- `run_id`
- `request_id`
- `agent_code`
- `run_status`
- `trigger_source`
- `external_contact_id`
- `userid`
- `task_id`
- `workflow_id`
- `started_at`
- `finished_at`
- `duration_ms`
- `error_code`
- `error_message`
- `output_count`
- `metadata`
- `created_at`
- `updated_at`

Production data is not allowed in the fixture seed.

## List Contract

The list contract should support:

- `page`
- `page_size`
- `request_id`
- `run_id`
- `agent_code`
- `run_status`
- `trigger_source`
- `external_contact_id`
- `userid`
- `task_id`
- `workflow_id`
- `started_after`
- `started_before`
- `has_error`

Response keys:

- `ok`
- `source_status`
- `route_owner`
- `page`
- `page_size`
- `total`
- `rows`
- `filters`
- `side_effect_safety`

Ordering must be `started_at_desc_id_desc`.

## Detail Contract

The detail contract should return:

- `ok`
- `run`
- `side_effect_safety`

Missing run IDs must return a not-found response shape without side effects.

## Visibility Contract

The fixture/native contract must preserve visibility behavior:

- masked visibility is required for external/contact identity by default;
- console visibility is allowed only as a fixture response mode;
- run metadata must not be treated as production evidence;
- output payloads are not included in the first metadata subset;
- production data remains disallowed.

## Excluded Scope

- run creation
- run execution
- agent replay
- agent orchestration
- agent output generation
- LLM generation
- DeepSeek adapter
- OpenClaw/MCP call
- WeCom, Payment, OAuth call
- workflow execution
- timer execution
- outbound send
- production data connection
- production write
- production route owner switch
- fallback removal
- `production_compat` change

## Side-Effect Safety

All side-effect flags remain false:

- real external call
- run creation
- run execution
- replay execution
- orchestration execution
- agent output generation
- LLM generation
- DeepSeek adapter
- OpenClaw/MCP call
- workflow execution
- timer execution
- outbound send
- production data

## Business continuity

Production continues to use the existing legacy-forwarded agent-run APIs. This PR does not connect to staging DB or production DB, does not execute staging smoke, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable run creation, run execution, replay, orchestration, output generation, LLM generation, DeepSeek, OpenClaw/MCP, WeCom, Payment, OAuth, workflow execution, timer execution, outbound send, or real external calls.

## Business value

This package defines the fixture/native contract needed to safely compare future Next behavior for agent-run metadata list/detail. It keeps execution history review useful while preserving strict separation from run creation, execution, replay, orchestration, generation, and external-call risk.

## Risk / rollback

Risk is limited to docs/checker/test/state drift. Rollback is to remove the Phase 4BO docs/YAML/checker/test changes and restore `phase_execution_state.yaml` to the previous Phase 4BN state. Runtime behavior is unchanged.

## Autopilot decision

Phase 4BO plans fixture/native contracts for agent-runs metadata list/detail only. Runtime implementation, production dry-run, production write, production repository route enablement, route ownership switch, fallback removal, real external calls, run creation, run execution, replay, orchestration, output generation, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer execution, outbound send, canary approval, and delete readiness remain unauthorized.

## Next action

Phase 4BP should create a docs-only owner decision package for agent-runs fixture/native runtime implementation. It must not implement runtime behavior, create or execute runs, trigger replay/orchestration, generate outputs, switch production owner, write production, execute external calls, remove fallback, or expand into generation/runtime paths.
