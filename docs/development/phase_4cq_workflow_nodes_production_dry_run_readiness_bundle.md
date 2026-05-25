# Phase 4CQ Workflow Nodes Production Read-Only Dry-Run Readiness

## Summary

Phase 4CQ creates the production read-only dry-run readiness bundle for `/api/admin/automation-conversion/workflow-nodes*`.

Bundle type: production read-only dry-run readiness bundle.

Included stages:

- Production read-only dry-run runner.
- Production read-only evidence gate.
- Blocked evidence output when approval/config is absent.
- Checker and tests.
- Phase state update.

Excluded stages:

- Production owner switch.
- Production write.
- Production repository route enablement.
- `production_compat` behavior change.
- Fallback removal or narrowing.
- Live external calls.
- Timer, workflow, task, agent, run-due, or outbound-send execution.
- Destructive migration, canary approval, or delete readiness.

## Architecture Boundary

Capability owner: `aicrm_next.automation_engine`.

Route family: `/api/admin/automation-conversion/workflow-nodes*`.

Current production owner remains `production_compat` with legacy fallback. This bundle does not change route ownership, runtime registration, production facade behavior, or fallback behavior.

## Runtime Behavior

Tool:

```bash
python3 tools/run_phase4cq_workflow_nodes_production_readonly_dry_run.py \
  --output-json /tmp/phase4cq_workflow_nodes_production_readonly_dry_run.json \
  --output-md /tmp/phase4cq_workflow_nodes_production_readonly_dry_run.md
```

Default behavior is blocked evidence only. With no approval/config, the tool does not connect to any DB and does not claim dry-run success.

Future owner-approved read-only execution requires all gates:

```bash
AICRM_PHASE4CQ_PRODUCTION_READONLY_DRY_RUN_APPROVED=1 \
AICRM_PHASE4CQ_PRODUCTION_CONFIG_REVIEWED=1 \
AICRM_WORKFLOW_NODES_REPO_BACKEND=sqlalchemy \
AICRM_WORKFLOW_NODES_READONLY_DRY_RUN_DATABASE_URL=<redacted-readonly-db-url> \
python3 tools/run_phase4cq_workflow_nodes_production_readonly_dry_run.py \
  --read-only \
  --confirm-no-writes \
  --output-json /tmp/phase4cq_workflow_nodes_production_readonly_dry_run.json \
  --output-md /tmp/phase4cq_workflow_nodes_production_readonly_dry_run.md
```

The runner only performs a list-read summary if all gates are present. It never uses `DATABASE_URL`, test DB, staging DB, fixture, local contract, or demo fallback as production dry-run evidence.

## Production Behavior

Production route owner is unchanged. Legacy fallback remains available. Fixture/local/demo data must not be returned as production success.

## Fallback Behavior

Legacy fallback is retained. No fallback is removed, narrowed, or bypassed.

## Verification

- `python3 tools/check_phase4cq_workflow_nodes_production_dry_run_readiness_bundle.py`
- `python3 -m pytest tests/test_phase4cq_workflow_nodes_production_dry_run_readiness_bundle.py -q`
- Required global autopilot checks after this diff exists.

## Risk / Rollback

Risk is limited to a disabled-by-default evidence tool and state/checker documentation. Rollback is to revert this PR. Since no production write, route switch, fallback removal, or production_compat change is included, production traffic remains on the current legacy fallback path.

## Business Continuity

This bundle helps operators keep the current automation-conversion workflow-nodes path stable while preparing evidence for a future read-only production comparison. Existing production behavior stays legacy-forwarded, so daily automation configuration is not interrupted.

## Business Value

The business value is safer migration confidence: workflow-nodes can gather future read-only shape/count evidence without enabling writes, external calls, or owner switching. Blocked evidence also makes missing approvals/config visible instead of pretending the route is ready.

## Autopilot Decision

Autopilot created this bounded Phase 4 bundle because workflow-nodes already has fixture/runtime, repository adapter parity, and staging readiness. The next safe vertical step is production read-only dry-run readiness.

## Baseline Blockers

Known existing baseline blockers on `main`:

- `aicrm_next/automation_engine/group_ops/domain.py` imports `wecom_ability_service.domains.tasks.private_message`.
- `aicrm_next/integration_gateway/wecom_group_adapter.py` imports `wecom_ability_service.wecom_client`.
- `aicrm_next/integration_gateway/wecom_group_adapter.py` imports `wecom_ability_service.domains.broadcast_jobs`.

This PR does not touch those files and does not add new legacy facade growth.

## Smaller PRs Replaced / Estimated PR-Count Reduction

This bundle replaces separate PRs for production dry-run planning, runner, evidence gate, checker/test, and phase state. Estimated PR-count reduction: 50%.

## Next Bundle Recommendation

Next bundle: `phase_4cr_tasks_production_dry_run_readiness_bundle` for `/api/admin/automation-conversion/tasks*`, with the same no-write, no-owner-switch, no-fallback-removal boundary.
