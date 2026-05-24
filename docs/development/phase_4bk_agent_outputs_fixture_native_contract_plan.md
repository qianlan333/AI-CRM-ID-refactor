# Phase 4BK Agent Outputs Fixture Native Contract Planning

Phase 4BK plans a fixture/native contract for the first `/api/admin/automation-conversion/agent-outputs*` read-only metadata subset. This is a no-runtime-change autopilot work package.

## Summary

- Active candidate: `/api/admin/automation-conversion/agent-outputs*`.
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

- `GET /api/admin/automation-conversion/agent-outputs`
- `GET /api/admin/automation-conversion/agent-outputs/{output_id}`

Both routes are read-only metadata surfaces. The plan requires deterministic fixture rows and read responses only.

## Fixture Seed

The fixture seed should include two deterministic agent output rows:

- `phase4bk_output_reply_draft`
- `phase4bk_output_route_decision`

Required fields:

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
- `created_at`

Production data is not allowed in the fixture seed.

## List Contract

The list contract should support:

- `page`
- `page_size`
- `request_id`
- `external_contact_id`
- `userid`
- `agent_code`
- `output_type`
- `applied_status`
- `min_confidence`
- `max_confidence`
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

Ordering must be `created_at_desc_id_desc`.

## Detail Contract

The detail contract should return:

- `ok`
- `output`
- `run`
- `side_effect_safety`

Missing output IDs must return a not-found response shape without side effects.

## Visibility Contract

The fixture/native contract must preserve visibility behavior:

- masked visibility is required for external/contact identity by default;
- console visibility is allowed only as a fixture response mode;
- raw output and normalized payloads must not be treated as production evidence;
- production data remains disallowed.

## Excluded Scope

- export job creation
- export job status lookup
- file download
- agent-runs
- agent replay
- agent orchestration
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
- export job creation
- file download
- agent-run execution
- LLM generation
- DeepSeek adapter
- OpenClaw/MCP call
- workflow execution
- timer execution
- outbound send
- production data

## Business continuity

Production continues to use the existing legacy-forwarded agent output APIs. This PR does not connect to staging DB or production DB, does not execute staging smoke, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable export job creation, file download, agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, WeCom, Payment, OAuth, workflow execution, timer execution, outbound send, or real external calls.

## Business value

This package defines the fixture/native contract needed to safely compare future Next behavior for agent output list/detail metadata. It keeps generated-content review useful while preserving strict separation from export/download, runtime execution, generation, and external-call risk.

## Risk / rollback

Risk is limited to docs/checker/test/state drift. Rollback is to remove the Phase 4BK docs/YAML/checker/test changes and restore `phase_execution_state.yaml` to the previous Phase 4BJ state. Runtime behavior is unchanged.

## Autopilot decision

Phase 4BK plans fixture/native contracts for agent-outputs metadata list/detail only. Runtime implementation, production dry-run, production write, production repository route enablement, route ownership switch, fallback removal, real external calls, export job creation, file download, agent-run execution, LLM generation, DeepSeek, OpenClaw/MCP, workflow execution, timer execution, outbound send, canary approval, and delete readiness remain unauthorized.

## Next action

Phase 4BL should create a docs-only owner decision package for agent-outputs fixture/native runtime implementation. It must not implement runtime behavior, create export jobs, download files, switch production owner, write production, execute external calls, remove fallback, or expand into agent-runs/replay/orchestration/generation.
