# Phase 4BA Tasks Metadata Planning

## Summary

Phase 4BA starts the `/api/admin/automation-conversion/tasks*` internal_write chain with a metadata-only planning package. It records the safe subset, future contract-planning boundaries, required guardrails, and the next Phase 4BB step.

This PR is planning/checker/test/state only. It does not implement a Next runtime path, does not execute staging smoke, and does not change production behavior.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Route family: `/api/admin/automation-conversion/tasks*`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback is retained.
- Fixture/local evidence is not production success.

## Business continuity

Production continues to use the existing legacy-forwarded task APIs. This package does not connect to staging DB or production DB, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable task execution, workflow execution, timer execution, outbound send, or real external calls.

## Business value

The tasks route family is a daily operational surface for automation configuration, so the first safe step is to isolate metadata planning from execution behavior. This gives later Phase 4BB/4BC work a bounded contract path while preserving current operations and preventing accidental run-due or workflow execution changes.

## Planned Metadata Subset

Phase 4BA limits future contract planning to metadata list/create shape for:

- task identity and display fields;
- group/workflow relationships as references only;
- task type/status/trigger policy metadata;
- scheduling policy as stored configuration only;
- priority, owner role, audit timestamps, and optional tags/description/metadata.

The metadata subset explicitly excludes runtime execution and side effects.

## Excluded Scope

- `/api/admin/automation-conversion/tasks/run-due`
- task detail/update/delete expansion
- workflow execution
- task execution
- timer execution
- outbound send
- external calls
- production data connection
- production write
- production route owner switch
- fallback removal
- `production_compat` change

## Required Guardrails

- Keep legacy fallback.
- Confirm route surface before fixture/native contract planning.
- Treat run-due and execution routes as out of scope.
- Require idempotency, audit, rollback payload, and dangerous-field rejection for later create contract planning.
- Keep fixture/local evidence out of production claims.
- Require explicit owner approval before any runtime implementation, staging execution, production write, owner switch, or fallback removal.

## Verification

- `python3 tools/check_phase4ba_tasks_metadata_plan.py --output-md /tmp/phase4ba_tasks_metadata_plan.md --output-json /tmp/phase4ba_tasks_metadata_plan.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4ba_tasks_metadata_plan.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to planning/checker misclassification. Rollback is to revert the Phase 4BA docs/YAML/checker/test/state updates. Production traffic remains on `production_compat` / legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BA tasks metadata planning. The package advances the tasks chain without runtime changes and records Phase 4BB as the next allowed action.

## Next action

Phase 4BB should confirm the tasks route surface and schema/table references for the metadata-only subset. It must not implement runtime ownership, execute run-due, write production, switch production owner, remove fallback, or enable real external calls.
