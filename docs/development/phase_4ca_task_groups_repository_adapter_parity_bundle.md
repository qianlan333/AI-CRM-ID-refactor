# Phase 4CA Task Groups Repository Adapter Parity Bundle

## Summary

Phase 4CA bundles the safe repository-adapter parity stage for `/api/admin/automation-conversion/task-groups*`. It adds an explicit SQLAlchemy adapter for task-group metadata, a route-specific local/test DB parity harness, checker coverage, runtime tests, and phase state advancement.

The adapter is disabled by default. It requires `AICRM_TASK_GROUPS_REPO_BACKEND=sqlalchemy` and a route-specific `AICRM_TASK_GROUPS_TEST_DATABASE_URL` or `AICRM_TASK_GROUPS_STAGING_DATABASE_URL`; it never falls back to `DATABASE_URL`. The default backend remains fixture/local.

## Bundle Type

Repository adapter parity bundle.

## Included Stages

- Repository adapter plan.
- SQLAlchemy adapter behind an explicit backend flag.
- Test DB parity harness.
- Additive idempotency, audit, and rollback scaffolding.
- Checker and tests.
- `phase_execution_state.yaml` update.

## Excluded Stages

- Production route owner switch.
- Production repository enablement as active route owner.
- Production DB fallback or generic `DATABASE_URL` fallback.
- Automatic production writes.
- Fallback removal or narrowing.
- Destructive migrations.
- Live external calls.
- Timer, run-due, workflow execution, task execution, or outbound send.
- Canary approval or `delete_ready=true`.

## Route Family

`/api/admin/automation-conversion/task-groups*`

## Runtime Behavior, If Any

Runtime behavior is limited to an opt-in repository adapter for task-group metadata list/create parity. The default `build_automation_repository()` path continues to return fixture/local behavior. The SQLAlchemy path is only selected when the explicit task-groups backend flag is set or when tests inject an engine directly.

## Production Behavior

Production behavior is unchanged. The production route owner remains `production_compat` / `legacy_forward`, and production must not return fixture fake success. This bundle does not authorize production writes or production DB use.

## Fallback Behavior

Legacy fallback is retained. Rollback is to unset `AICRM_TASK_GROUPS_REPO_BACKEND` or revert this PR.

## Business Continuity

Current automation task-group operations remain on the existing production compatibility path. The adapter can be exercised against local/test DBs without changing production routing, allowing parity work to proceed while protecting live operations.

## Business Value

This bundle reduces PR churn by combining adapter planning, implementation, test DB parity, audit/idempotency/rollback scaffolding, checker coverage, and state updates. It gives the migration path a concrete parity harness without enabling production writes.

## Safety / Non-Goals

- No `DATABASE_URL` fallback.
- No production route switch.
- No production write by default.
- No external calls by default.
- No timer/execution/outbound send by default.
- Legacy fallback retained.
- Production must not return fixture fake success.

## Verification

- `python3 tools/check_phase4ca_task_groups_repository_adapter_parity_bundle.py --output-md /tmp/phase4ca_task_groups_repository_adapter_parity_bundle.md --output-json /tmp/phase4ca_task_groups_repository_adapter_parity_bundle.json`
- `python3 tools/run_phase4ca_task_groups_adapter_parity.py --output-md /tmp/phase4ca_task_groups_adapter_parity.md --output-json /tmp/phase4ca_task_groups_adapter_parity.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4ca_task_groups_repository_adapter_parity_bundle.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is limited to disabled-by-default adapter defects or checker misclassification. Rollback is to revert the PR or unset the backend flag. Since production routing and fallback remain unchanged, rollback does not affect live traffic.

## Autopilot Decision

Autopilot selected a compressed repository adapter parity bundle for the completed task-groups fixture/native runtime slice.

## PR Lifecycle

This PR is autopilot-safe when the package checker and standard eligibility gate pass, the diff remains within the repository adapter parity boundary, and GitHub required checks are green.

## Next Bundle Recommendation

Proceed to `phase_4cb_workflows_repository_adapter_parity_bundle` for `/api/admin/automation-conversion/workflows*`.
