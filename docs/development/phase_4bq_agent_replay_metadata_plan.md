# Phase 4BQ Agent Replay Metadata Planning

## Summary

Phase 4BQ starts the `/api/admin/automation-conversion/agent-replay` readonly chain with metadata-only planning. It records the route inventory, candidate read model, future checker/test expectations, and the next safe Phase 4BR schema/route confirmation step.

This package is docs/tools/tests/state only. It does not implement replay runtime, does not create or execute runs, does not execute staging smoke, and does not change production behavior.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Route family: `/api/admin/automation-conversion/agent-replay`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback is retained.
- Fixture/local evidence is not production evidence.

## Business continuity

Production continues to use the existing legacy-forwarded replay API. This package does not connect to staging DB or production DB, does not execute staging smoke, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable replay execution, run creation, run execution, orchestration, agent-output generation, LLM generation, DeepSeek, OpenClaw/MCP, WeCom, Payment, OAuth, workflow execution, timer execution, outbound send, or real external calls.

## Business value

Agent replay sits next to automation execution and generated-output surfaces, so it needs a stricter boundary than ordinary read-only metadata. Starting with metadata planning lets Phase 4 document what can be safely described later, while keeping actual replay execution, run creation, orchestration, generated outputs, adapters, and external calls out of the autopilot lane.

## Planned Metadata Subset

Phase 4BQ limits future contract planning to replay metadata inventory for:

- replay request identity and source run reference;
- agent code, trigger source, and requester/operator references;
- replay status as metadata only;
- timestamps and optional duration/error metadata;
- side-effect safety flags that explain why no execution happened;
- masked payload or input reference identifiers, not raw production data.

The metadata subset explicitly excludes creating a replay, executing a replay, creating or executing runs, orchestration, output generation, delivery, and side effects.

## Included Route Inventory

- `GET /api/admin/automation-conversion/agent-replay`

This is an inventory target for later schema/route confirmation only. This package does not implement or execute it.

## Excluded Scope

- `POST /api/admin/automation-conversion/agent-runs`
- `/api/admin/automation-conversion/agent-runs/{run_id}/execute`
- `/api/admin/automation-conversion/agent-orchestration*`
- `/api/admin/automation-conversion/agent-outputs*`
- replay creation or execution
- run creation or execution
- orchestration execution
- agent-output generation
- LLM generation and DeepSeek adapter calls
- OpenClaw/MCP calls
- WeCom, Payment, OAuth calls
- workflow execution
- timer execution
- outbound send
- production data connection
- production write
- production route owner switch
- fallback removal
- `production_compat` change

## Required Guardrails

- Keep legacy fallback.
- Treat the route inventory as read-only planning until a later package confirms schema and route surface.
- Keep replay execution, run creation, and run execution out of scope.
- Keep orchestration, agent-output generation, LLM generation, DeepSeek, OpenClaw/MCP, and real external calls out of scope.
- Require masked visibility and no production data for future fixture/native planning.
- Keep fixture/local evidence out of production claims.
- Require explicit owner approval before any runtime implementation that would execute replay, create runs, execute runs, call adapters, write production, switch owner, or remove fallback.

## Verification

- `python3 tools/check_phase4bq_agent_replay_metadata_plan.py --output-md /tmp/phase4bq_agent_replay_metadata_plan.md --output-json /tmp/phase4bq_agent_replay_metadata_plan.json`
- `python3 tools/check_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py --output-md /tmp/phase4bp_agent_runs_owner_decision.md --output-json /tmp/phase4bp_agent_runs_owner_decision.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py tests/test_phase4bq_agent_replay_metadata_plan.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to planning/checker misclassification. Rollback is to revert the Phase 4BQ docs/YAML/checker/test/state updates. Production traffic remains on `production_compat` / legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BQ agent-replay metadata planning. The package advances the agent-replay chain without runtime changes and records Phase 4BR as the next allowed action.

## Next action

Phase 4BR should confirm the agent-replay schema and route surface for the read-only metadata subset. It must not implement runtime ownership, create or execute runs, trigger replay/orchestration, generate outputs, enable LLM generation, call DeepSeek/OpenClaw/MCP, write production, switch production owner, remove fallback, or enable real external calls.
