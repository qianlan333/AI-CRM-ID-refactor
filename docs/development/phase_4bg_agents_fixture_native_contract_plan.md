# Phase 4BG Agents Fixture Native Contract Plan

Phase 4BG plans a fixture/native contract for the metadata-only subset of `/api/admin/automation-conversion/agents*`. This is a no-runtime-change package.

## Summary

- Active candidate: `/api/admin/automation-conversion/agents*`.
- Capability owner: `aicrm_next.automation_engine`.
- Integration fallback boundary: `aicrm_next.integration_gateway`.
- Current production owner: `production_compat`.
- Current production behavior: `legacy_forward`.
- Legacy fallback retained: true.
- Fixture/local evidence is not production success.

## Planned Fixture Routes

The future fixture/native contract is limited to:

- `GET /api/admin/automation-conversion/agents/options`
- `POST /api/admin/automation-conversion/agents`

The GET path represents metadata list/options only. The POST path represents metadata-only create only.

## Fixture Seed

The deterministic fixture set should include:

- `phase4bg_conversion_followup_agent`
- `phase4bg_safety_review_agent`

Required metadata fields:

- `id`
- `agent_code`
- `display_name`
- `description`
- `scenario_code`
- `enabled`
- `prompt_template_code`
- `tool_policy_code`
- `model_policy_code`
- `created_at`
- `updated_at`

Production data is not allowed in fixture seed data.

## List Contract

Query keys:

- `enabled_only`
- `keyword`
- `scenario_code`

Response keys:

- `ok`
- `source_status`
- `route_owner`
- `agents`
- `options`
- `total`
- `count`
- `filters`
- `side_effect_safety`

Runtime rows are excluded. Ordering should be `enabled_desc_updated_at_desc_agent_code_asc`.

## Create Contract

Required payload:

- `agent_code`
- `display_name`
- `idempotency_key`

Optional payload:

- `description`
- `scenario_code`
- `enabled`
- `prompt_template_code`
- `tool_policy_code`
- `model_policy_code`
- `operator`

Response keys:

- `ok`
- `agent`
- `audit_event`
- `rollback_payload`
- `idempotent_replay`
- `side_effect_safety`

The contract must reject missing `agent_code`, missing `display_name`, invalid `enabled`, dangerous fields, and execution fields.

## Idempotency / Audit

The fixture/native contract must require:

- route-family scope
- operation scope
- operator scope
- `agent_code` scope
- `idempotency_key`
- same-hash replay
- different-hash conflict
- audit event
- after snapshot
- rollback payload
- side-effect safety marker

## Excluded Scope

These paths and behaviors remain outside Phase 4BG:

- agent detail
- agent draft
- agent publish
- agent delete
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
- production data connection
- production write
- production route owner switch
- fallback removal

## Business Continuity

This PR only records Phase 4BG agents fixture/native contract planning and updates static docs/tools/tests/state. It does not connect to staging DB or production data, does not execute staging smoke, does not write production, does not enable production repository as route owner, does not switch production route owner, does not delete legacy fallback, does not modify `production_compat`, and does not affect current automation conversion agents page/API daily use.

## Risk / Rollback

Risk is limited to docs/checker/test/state drift. Rollback is to remove the Phase 4BG docs/YAML/checker/test changes and restore `phase_execution_state.yaml` to the previous Phase 4BF state. Runtime behavior is unchanged.

## Phase 4BG Decision

Phase 4BG defines a fixture/native contract plan for agents metadata list/create only. Runtime implementation, production dry-run, production write, production repository route enablement, route ownership switch, fallback removal, real external calls, agent-run execution, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer execution, outbound send, canary approval, and delete readiness remain unauthorized.

## Next Action

Phase 4BH should create an owner decision package for agents fixture/native runtime implementation. It must not implement runtime behavior, switch production owner, write production, execute external calls, remove fallback, or expand into agent-runs/outputs/detail/update/delete/draft/publish.
