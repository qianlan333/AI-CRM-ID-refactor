# Phase 4BM Agent Runs Metadata Planning

## Summary

Phase 4BM starts the `/api/admin/automation-conversion/agent-runs*` internal_write chain with metadata-only planning. It records the read-only agent-run metadata subset, route boundaries, future checker/test expectations, and the next safe Phase 4BN step.

This package is docs/tools/tests/state only. It does not implement a native runtime path, does not execute staging smoke, and does not change production behavior.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Route family: `/api/admin/automation-conversion/agent-runs*`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback is retained.
- Fixture/local evidence is not production evidence.

## Business continuity

Production continues to use the existing legacy-forwarded agent-run APIs. This package does not connect to staging DB or production DB, does not execute staging smoke, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable run creation, run execution, replay, orchestration, agent-output generation, LLM generation, DeepSeek, OpenClaw/MCP, WeCom, Payment, OAuth, workflow execution, timer execution, outbound send, or real external calls.

## Business value

Agent runs are operational trace metadata for automation conversion work, but they sit directly beside execution, replay, orchestration, generated outputs, and external-call surfaces. Starting with read-only metadata planning lets Phase 4 clarify the safe list/detail inventory while keeping run creation, run execution, replay/orchestration, generation, adapters, and external calls explicitly out of scope. That keeps overnight autopilot progress useful without disturbing current operations.

## Planned Metadata Subset

Phase 4BM limits future contract planning to read-only metadata inventory for:

- run identity and request references;
- agent code and trigger source;
- run status and timestamps;
- optional contact/user/task/workflow references;
- optional duration, error, output count, and metadata payload references.

The metadata subset explicitly excludes run creation, run execution, replay, orchestration, output generation, delivery, and side effects.

## Included Route Inventory

- `GET /api/admin/automation-conversion/agent-runs`
- `GET /api/admin/automation-conversion/agent-runs/{run_id}`

These are inventory targets for later schema/route confirmation only. This package does not implement or execute them.

## Excluded Scope

- `POST /api/admin/automation-conversion/agent-runs`
- `/api/admin/automation-conversion/agent-runs/{run_id}/execute`
- `/api/admin/automation-conversion/agent-replay`
- `/api/admin/automation-conversion/agent-orchestration*`
- `/api/admin/automation-conversion/agent-outputs*` expansion
- run creation, update, delete, or execution
- replay or orchestration execution
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
- Treat list/detail route inventory as read-only planning until a later package confirms schema and route surface.
- Keep run creation and execution out of scope.
- Keep replay/orchestration, agent-output generation, LLM generation, DeepSeek, OpenClaw/MCP, and real external calls out of scope.
- Require pagination, masked visibility, and no production data for future fixture/native planning.
- Keep fixture/local evidence out of production claims.
- Require explicit owner approval before any runtime implementation, staging execution, production write, owner switch, fallback removal, generation, run execution, or external-call enablement.

## Verification

- `python3 tools/check_phase4bm_agent_runs_metadata_plan.py --output-md /tmp/phase4bm_agent_runs_metadata_plan.md --output-json /tmp/phase4bm_agent_runs_metadata_plan.json`
- `python3 tools/check_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py --output-md /tmp/phase4bl_agent_outputs_owner_decision.md --output-json /tmp/phase4bl_agent_outputs_owner_decision.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py tests/test_phase4bm_agent_runs_metadata_plan.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to planning/checker misclassification. Rollback is to revert the Phase 4BM docs/YAML/checker/test/state updates. Production traffic remains on `production_compat` / legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BM agent-runs metadata planning. The package advances the agent-runs chain without runtime changes and records Phase 4BN as the next allowed action.

## Next action

Phase 4BN should confirm the agent-runs schema and route surface for the read-only metadata list/detail subset. It must not implement runtime ownership, create or execute runs, trigger replay/orchestration, generate outputs, enable LLM generation, call DeepSeek/OpenClaw/MCP, write production, switch production owner, remove fallback, or enable real external calls.
