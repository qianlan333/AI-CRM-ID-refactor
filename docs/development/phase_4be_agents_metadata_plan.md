# Phase 4BE Agents Metadata Planning

## Summary

Phase 4BE starts the `/api/admin/automation-conversion/agents*` internal_write chain with a metadata-only planning package. It records the safe subset, future contract-planning boundaries, required guardrails, and the next Phase 4BF step.

This PR is planning/checker/test/state only. It does not implement a Next runtime path, does not execute staging smoke, and does not change production behavior.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Route family: `/api/admin/automation-conversion/agents*`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback is retained.
- Fixture/local evidence is not production success.

## Business continuity

Production continues to use the existing legacy-forwarded agent APIs. This package does not connect to staging DB or production DB, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, WeCom, Payment, OAuth, workflow execution, timer execution, outbound send, or real external calls.

## Business value

Agents are part of automation configuration, but they sit close to AI generation and runtime execution surfaces. Starting with metadata-only planning lets Phase 4 clarify the safe list/create contract boundary while keeping agent-runs, LLM adapters, and external calls explicitly out of scope. This supports future migration work without disturbing current operational pages.

## Planned Metadata Subset

Phase 4BE limits future contract planning to metadata list/create shape for:

- agent identity and display fields;
- status, type, owner role, and policy references;
- prompt/template/model/tool policy references as stored metadata only;
- audit timestamps and optional tags/description/metadata.

The metadata subset explicitly excludes runtime execution, generation, and side effects.

## Excluded Scope

- `/api/admin/automation-conversion/agent-runs*`
- `/api/admin/automation-conversion/agent-outputs*`
- `/api/admin/automation-conversion/agent-replay`
- `/api/admin/automation-conversion/agent-orchestration*`
- agent detail/update/delete expansion
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
- Confirm route surface before fixture/native contract planning.
- Treat agent-runs, outputs, replay, orchestration, and detail/update/delete routes as out of scope.
- Require idempotency, audit, rollback payload, and dangerous-field rejection for later create contract planning.
- Keep fixture/local evidence out of production claims.
- Require explicit owner approval before any runtime implementation, staging execution, production write, owner switch, fallback removal, LLM generation, or external-call enablement.

## Verification

- `python3 tools/check_phase4be_agents_metadata_plan.py --output-md /tmp/phase4be_agents_metadata_plan.md --output-json /tmp/phase4be_agents_metadata_plan.json`
- `python3 tools/check_phase4bd_tasks_fixture_native_implementation_owner_decision.py --output-md /tmp/phase4bd_tasks_fixture_native_implementation_owner_decision.md --output-json /tmp/phase4bd_tasks_fixture_native_implementation_owner_decision.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bd_tasks_fixture_native_implementation_owner_decision.py tests/test_phase4be_agents_metadata_plan.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to planning/checker misclassification. Rollback is to revert the Phase 4BE docs/YAML/checker/test/state updates. Production traffic remains on `production_compat` / legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BE agents metadata planning. The package advances the agents chain without runtime changes and records Phase 4BF as the next allowed action.

## Next action

Phase 4BF should confirm the agents route surface and schema/table references for the metadata-only subset. It must not implement runtime ownership, execute agent-runs, enable LLM generation, call DeepSeek/OpenClaw/MCP, write production, switch production owner, remove fallback, or enable real external calls.
