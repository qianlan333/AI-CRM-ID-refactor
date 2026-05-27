# Post-Phase 7 Cleanup Owner Evidence Package Generation

## Status

- status: `post_phase7_cleanup_owner_evidence_package_generation`
- bundle type: `post_phase7_cleanup_owner_evidence_package_generation_bundle`
- cleanup family: `owner_evidence_package_generation`
- latest main SHA reviewed: `08f2a2255c389a244e1667fe92e9cb1431b135d8`
- no fallback removal
- no production_compat cleanup
- no production_compat behavior change
- no wildcard cleanup
- no runtime deletion
- no production behavior change
- no delete_ready=true

This package follows PR #806, which paused the cleanup track until owner evidence exists. It collects the evidence that can be derived from current repository artifacts and keeps owner-only fields explicit. It does not execute cleanup.

## Source Evidence

- PR #798 task-groups evidence refresh: task-groups cleanup remains blocked by missing route-specific owner approval, latest-main shadow compare, rollback owner, rollback plan, rollback execution evidence, route ownership proof, and production_compat exact-entry proof.
- PR #799 workflow-nodes evidence refresh: workflow-nodes cleanup remains blocked by the same evidence categories.
- PR #801 cleanup blocker acceptance: task-groups and workflow-nodes must not proceed to fallback removal or production_compat cleanup without complete route-specific evidence.
- PR #802 owner evidence collection: both route families were converted into an owner-action matrix.
- PR #806 owner evidence waiting acceptance: cleanup track status is `paused_waiting_owner_evidence`.

## Evidence Package Matrix

| Route family | Owner approval | Latest-main shadow compare | Rollback owner | Rollback plan | Rollback execution evidence | Route ownership proof | production_compat exact-entry proof | Ready for validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/automation-conversion/task-groups*` | owner_required | blocked runner evidence generated at `/tmp/task_groups_shadow_compare_package.json` | owner_required | draft generated in this doc | blocked runner evidence generated at `/tmp/task_groups_rollback_rehearsal_package.json` | collected from `docs/route_ownership/production_route_ownership_manifest.yaml` | collected from manifest and Phase 6H exact-route proposal | false |
| `/api/admin/automation-conversion/workflow-nodes*` | owner_required | blocked runner evidence generated at `/tmp/workflow_nodes_shadow_compare_package.json` | owner_required | draft generated in this doc | owner_required; no route-specific rollback runner exists in the repo | collected from `docs/route_ownership/production_route_ownership_manifest.yaml` | collected from manifest and Phase 6H exact-route proposal | false |

## Collected Route Ownership Proof

`docs/route_ownership/production_route_ownership_manifest.yaml` contains exact route-family entries for:

- `/api/admin/automation-conversion/task-groups*`
- `/api/admin/automation-conversion/workflow-nodes*`

Both entries currently state:

- capability owner: `aicrm_next.automation_engine`
- current runtime owner: `production_compat`
- production behavior: `legacy_forward`
- legacy fallback allowed: `true`
- delete_ready: `false`

That proves route ownership and also proves cleanup cannot proceed as a blind deletion.

## Generated Shadow Compare Evidence

The existing blocked-by-default tools were executed only to produce local evidence outputs. They do not switch owners, remove fallback, change production_compat, trigger timers, send outbound traffic, or set delete_ready.

- Task-groups command:
  `python3 tools/run_phase6c_task_groups_shadow_compare.py --confirm-fallback-retained --confirm-production-compat-unchanged --output-json /tmp/task_groups_shadow_compare_package.json`
- Workflow-nodes command:
  `python3 tools/run_phase6d_internal_metadata_owner_switch_batch.py --output-json /tmp/workflow_nodes_shadow_compare_package.json`
- production_compat exact-route proposal command:
  `python3 tools/run_phase6h_production_compat_exact_route_shadow_compare.py > /tmp/production_compat_exact_route_shadow_compare_package.json`

The outputs remain blocked-by-default evidence, not cleanup authorization.

## Rollback Plan Draft

For either selected route, a future exact-route cleanup retry must define a rollback plan that includes:

1. Re-enable the exact route fallback hook or production_compat entry that was changed.
2. Restore the route ownership manifest entry to the pre-cleanup value.
3. Re-run the route-specific shadow compare command against latest main.
4. Re-run the route-specific rollback rehearsal command and save output.
5. Confirm fallback retained, production_compat behavior unchanged except for the intended exact-route entry, runtime deletion not executed, timer/execution not triggered, outbound send not triggered, and delete_ready remains false.

This PR only drafts the plan. It does not assign the rollback owner and does not produce owner-approved rollback execution evidence.

## Owner Required Fields

The following fields cannot be inferred from repository artifacts and remain required before validation or cleanup retry:

- route-specific owner approval
- rollback owner
- rollback execution evidence for workflow-nodes
- risk acceptance
- approval timestamp

Because these owner-required fields remain incomplete, both route packages have `ready_for_validation: false`.

## Cleanup Decision

- task-groups ready for validation: false
- workflow-nodes ready for validation: false
- all blocked owner required: true
- fallback removals executed: []
- production_compat cleanups executed: []
- runtime deletions executed: []
- delete_ready: false

## Next Bundle Recommendation

If the owner supplies the missing evidence fields, the next bundle can be `post_phase7_cleanup_owner_evidence_validation_bundle`.

With the current repository evidence only, the next safe bundle is `post_phase7_cleanup_owner_evidence_package_blocker_acceptance_bundle`.
