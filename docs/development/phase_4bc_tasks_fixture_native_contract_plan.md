# Phase 4BC Tasks Fixture Native Contract Plan

## Summary

Phase 4BC plans the fixture/native list/create metadata contract for `/api/admin/automation-conversion/tasks*`. It does not implement runtime code. The contract is limited to deterministic fixture data, local list/create metadata behavior, idempotency, audit, rollback, and side-effect safety.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Current production owner remains `production_compat`.
- Production behavior remains `legacy_forward`.
- Legacy fallback remains retained.
- Fixture data is not allowed in production.

## Business continuity

Production continues to use the existing legacy-forwarded task APIs. This package does not connect to staging DB or production DB, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable task execution, workflow execution, timer execution, outbound send, or real external calls.

## Planned Fixture Routes

Phase 4BC only plans fixture/local contract behavior for:

- `GET /api/admin/automation-conversion/tasks`
- `POST /api/admin/automation-conversion/tasks`

The POST route is metadata-create only. A future fixture/native implementation must reject execution fields and return audit/rollback/side-effect-safety evidence.

## Deferred Scope

- task detail
- task update
- task copy
- task activate/pause
- task delete/archive
- preview audience
- run-due
- execution tables
- task execution
- workflow execution
- timer execution
- outbound send
- real external calls
- production write
- production owner switch
- fallback removal
- `production_compat` change

## Fixture Contract

The fixture seed must be deterministic and include two task records:

- `phase4bc_daily_followup_task`
- `phase4bc_audience_entered_task`

The list contract must return `groups`, `tasks`, `behavior_tiers`, `targetable_stages`, filters, counts, route owner, source status, and side-effect safety. Archived tasks are excluded by default.

The create contract must require `task_name` and `idempotency_key`, support only metadata fields, reject dangerous/execution fields, return audit/rollback evidence, and handle idempotent replay/conflict deterministically.

## Business value

This package gives the tasks migration a safe fixture/native contract target before any runtime implementation. It keeps current operations uninterrupted while making the future implementation testable for idempotency, rollback, and side-effect safety.

## Verification

- `python3 tools/check_phase4bc_tasks_fixture_native_contract_plan.py --output-md /tmp/phase4bc_tasks_fixture_native_contract_plan.md --output-json /tmp/phase4bc_tasks_fixture_native_contract_plan.json`
- `python3 tools/check_phase4bb_tasks_schema_route_surface_confirmation.py --output-md /tmp/phase4bb_tasks_schema_route_surface_confirmation.md --output-json /tmp/phase4bb_tasks_schema_route_surface_confirmation.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bb_tasks_schema_route_surface_confirmation.py tests/test_phase4bc_tasks_fixture_native_contract_plan.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to fixture contract planning/checker/state misclassification. Rollback is to revert this PR. Production traffic remains on `production_compat` and legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BC tasks fixture/native contract planning. Runtime implementation is not included and now requires a Phase 4BD owner decision package.

## Next action

Phase 4BD should create a tasks fixture/native implementation owner decision package. It must not implement runtime ownership, execute run-due, write production, switch production owner, remove fallback, enable outbound send, or enable real external calls.
