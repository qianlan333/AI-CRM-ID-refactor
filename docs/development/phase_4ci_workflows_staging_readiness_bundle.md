# Phase 4CI Workflows Staging Readiness Bundle

## Bundle Type

Staging readiness bundle.

## Included Stages

- Staging smoke plan for `/api/admin/automation-conversion/workflows*`.
- Disabled-by-default staging readiness preflight.
- Staging evidence gate with blocked evidence output when config or approval is missing.
- Checker and tests for staging DB safety, default blocked behavior, and phase state.
- `phase_execution_state.yaml` update for the next Phase 4 bundle.

## Excluded Stages

- Production DB access.
- Production write.
- Production route owner switch.
- Production repository enablement.
- Legacy fallback narrowing or removal.
- Live external calls.
- Timer, workflow, task, or outbound-send execution.
- Destructive migration.
- Canary approval or delete-ready approval.

## Route Family

`/api/admin/automation-conversion/workflows*`

## Runtime Behavior

This bundle adds a staging readiness runner only. By default it does not connect to a DB, does not execute staging smoke, and does not write staging data. It returns blocked evidence until `AICRM_WORKFLOWS_STAGING_DATABASE_URL`, `AICRM_WORKFLOWS_REPO_BACKEND=sqlalchemy`, and `AICRM_PHASE4CI_STAGING_SMOKE_APPROVED=1` are explicitly present.

The runner refuses production-looking URLs and never falls back to `DATABASE_URL` or the test DB URL.

## Production Behavior

Production owner is unchanged. The package does not authorize production DB access, production writes, production route owner switch, production repository route enablement, or fallback removal. Production must not return fixture fake success.

## Fallback Behavior

Legacy production fallback remains available. This bundle does not narrow or remove `production_compat`, legacy forwards, or wildcard fallback behavior.

## Verification

- `python3 tools/check_phase4ci_workflows_staging_readiness_bundle.py --output-md /tmp/phase4ci_workflows_staging_readiness_bundle.md --output-json /tmp/phase4ci_workflows_staging_readiness_bundle.json`
- `python3 tools/run_phase4ci_workflows_staging_readiness.py --output-md /tmp/phase4ci_workflows_staging_readiness.md --output-json /tmp/phase4ci_workflows_staging_readiness.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4ci_workflows_staging_readiness_bundle.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is limited to docs/tools/tests/state and a disabled-by-default staging preflight. Rollback is to revert this PR; fixture/local default, production legacy fallback, and production route ownership remain unchanged.

## Business Continuity

Current production users continue on the existing production-compatible route owner and legacy fallback. This bundle only prepares staging-readiness evidence for a future safe smoke step.

## Business Value

This gives operators an explicit, repeatable staging gate for workflows after fixture/native runtime and adapter parity are complete. It prevents missing staging configuration from being interpreted as readiness while moving Phase 4 toward staging evidence without production risk.

## Architecture Boundary

Capability owner: `aicrm_next.automation_engine`. This is canonical Phase 4 internal-write replacement preparation. It is not Phase 5 external adapter replacement, not Phase 6 `production_compat` narrowing/removal, and not Phase 7 legacy retirement.

## Safety / Non-Goals

No production write by default. No external calls by default. No timer, workflow, task, or outbound-send execution by default. No production owner switch, fallback removal, deploy config change, destructive migration, canary approval, or delete-ready approval.

## Autopilot Decision

Autopilot can classify this as deliverable when the package checker passes, required checks are green, and no forbidden live production/external behavior is enabled by default.

## Next Bundle Recommendation

Proceed to `phase_4cj_workflow_nodes_staging_readiness_bundle` for `/api/admin/automation-conversion/workflow-nodes*`, keeping staging smoke behavior disabled by default with blocked evidence when staging config is absent.

## PR Lifecycle

Create as a compressed Phase 4 bundle, wait for checks, then admin-merge only if the eligibility gate is true and GitHub required checks are green.

## Smaller PRs Replaced / Estimated PR-Count Reduction

This replaces separate PRs for staging smoke plan, staging preflight runner, evidence gate, blocked evidence output, checker/test updates, and phase-state handoff. Estimated PR-count reduction: 60 percent.
