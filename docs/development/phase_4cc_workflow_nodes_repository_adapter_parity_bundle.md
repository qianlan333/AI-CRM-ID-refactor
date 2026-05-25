# Phase 4CC Workflow Nodes Repository Adapter Parity Bundle

## Bundle Type

Repository adapter parity bundle.

## Included Stages

- Repository adapter plan for `/api/admin/automation-conversion/workflow-nodes*`.
- SQLAlchemy workflow-node metadata adapter behind `AICRM_WORKFLOW_NODES_REPO_BACKEND`.
- Route-specific test/staging DB URL gates through `AICRM_WORKFLOW_NODES_TEST_DATABASE_URL` or `AICRM_WORKFLOW_NODES_STAGING_DATABASE_URL`.
- Test DB parity harness for workflow-node list/create/idempotency/audit/rollback behavior.
- Additive idempotency, audit, and rollback scaffolding for metadata create only.
- Checker, tests, and `phase_execution_state.yaml` update.

## Excluded Stages

- Production route owner switch.
- Production DB fallback or `DATABASE_URL` fallback.
- Automatic production writes.
- Workflow execution, node transition runtime, timer execution, or outbound send.
- Fallback removal, destructive migrations, canary approval, or delete readiness.

## Route Family

`/api/admin/automation-conversion/workflow-nodes*`.

## Runtime Behavior

This bundle adds `SqlAlchemyWorkflowNodeRepository` for workflow-node metadata list/create parity against an explicitly configured test or staging database. The default repository backend remains fixture/local unless `AICRM_WORKFLOW_NODES_REPO_BACKEND` is explicitly set to a SQLAlchemy backend. Create uses a route-scoped idempotency table and emits audit evidence with all side-effect safety flags false.

## Production Behavior

Production owner is unchanged and production must not return fixture/local success as production success. The adapter has no `DATABASE_URL` fallback and does not enable production writes by default. Any later production-facing use still needs a separate approved bundle.

## Fallback Behavior

Legacy fallback remains available. This bundle does not narrow, remove, or reorder `production_compat` fallback.

## Verification

- `python3 tools/check_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py --output-md /tmp/phase4cc_workflow_nodes_repository_adapter_parity_bundle.md --output-json /tmp/phase4cc_workflow_nodes_repository_adapter_parity_bundle.json`
- `python3 tools/run_phase4cc_workflow_nodes_adapter_parity.py --output-md /tmp/phase4cc_workflow_nodes_adapter_parity.md --output-json /tmp/phase4cc_workflow_nodes_adapter_parity.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is limited to disabled-by-default adapter and test harness behavior. Rollback is to revert this bundle; fixture/local workflow-node behavior remains the default and legacy fallback remains in place.

## Next Bundle Recommendation

Proceed to `phase_4cd_tasks_repository_adapter_parity_bundle`, applying the same route-specific DB safety and disabled-by-default repository adapter parity boundary to `/api/admin/automation-conversion/tasks*`.
