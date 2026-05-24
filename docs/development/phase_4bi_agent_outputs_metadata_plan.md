# Phase 4BI Agent Outputs Metadata Planning

## Summary

Phase 4BI starts the `/api/admin/automation-conversion/agent-outputs*` internal_write chain with metadata-only planning. It records the read-only metadata subset, route boundaries, future checker/test expectations, and the next safe Phase 4BJ step.

This package is docs/tools/tests/state only. It does not implement a native runtime path, does not execute staging smoke, and does not change production behavior.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Route family: `/api/admin/automation-conversion/agent-outputs*`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback is retained.
- Fixture/local evidence is not production evidence.

## Business continuity

Production continues to use the existing legacy-forwarded agent output APIs. This package does not connect to staging DB or production DB, does not execute staging smoke, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable export job creation, file download, agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, WeCom, Payment, OAuth, workflow execution, timer execution, outbound send, or real external calls.

## Business value

Agent outputs are operational evidence for automation conversion work, but they sit close to generated content, export/download surfaces, and agent runtime execution. Starting with read-only metadata planning lets Phase 4 clarify the safe list/detail inventory while keeping export jobs, downloads, agent-runs, generation, adapters, and external calls explicitly out of scope. That keeps overnight autopilot progress useful without disturbing current operations.

## Planned Metadata Subset

Phase 4BI limits future contract planning to read-only metadata inventory for:

- output identity and source run references;
- agent code and output type;
- applied status and visibility;
- created/updated timestamps;
- optional summary, reason, confidence, request id, external contact id, and metadata payload references.

The metadata subset explicitly excludes export job creation, file download, generation, delivery, runtime execution, and side effects.

## Included Route Inventory

- `GET /api/admin/automation-conversion/agent-outputs`
- `GET /api/admin/automation-conversion/agent-outputs/{output_id}`

These are inventory targets for later schema/route confirmation only. This package does not implement or execute them.

## Excluded Scope

- `POST /api/admin/automation-conversion/agent-outputs/export`
- `GET /api/admin/automation-conversion/agent-outputs/export/{job_id}`
- `/api/admin/automation-conversion/agent-runs*`
- `/api/admin/automation-conversion/agents*` runtime expansion
- export job creation
- file download
- agent-run execution
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
- Keep export job creation and file download out of scope.
- Keep agent-runs, LLM generation, DeepSeek, OpenClaw/MCP, and real external calls out of scope.
- Require pagination, masked visibility, and no production data for future fixture/native planning.
- Keep fixture/local evidence out of production claims.
- Require explicit owner approval before any runtime implementation, staging execution, production write, owner switch, fallback removal, generation, export/download enablement, or external-call enablement.

## Verification

- `python3 tools/check_phase4bi_agent_outputs_metadata_plan.py --output-md /tmp/phase4bi_agent_outputs_metadata_plan.md --output-json /tmp/phase4bi_agent_outputs_metadata_plan.json`
- `python3 tools/check_phase4bh_agents_fixture_native_implementation_owner_decision.py --output-md /tmp/phase4bh_agents_owner_decision.md --output-json /tmp/phase4bh_agents_owner_decision.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bh_agents_fixture_native_implementation_owner_decision.py tests/test_phase4bi_agent_outputs_metadata_plan.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to planning/checker misclassification. Rollback is to revert the Phase 4BI docs/YAML/checker/test/state updates. Production traffic remains on `production_compat` / legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BI agent outputs metadata planning. The package advances the agent-outputs chain without runtime changes and records Phase 4BJ as the next allowed action.

## Next action

Phase 4BJ should confirm the agent-outputs schema and route surface for the read-only metadata list/detail subset. It must not implement runtime ownership, create export jobs, download files, execute agent-runs, enable LLM generation, call DeepSeek/OpenClaw/MCP, write production, switch production owner, remove fallback, or enable real external calls.
