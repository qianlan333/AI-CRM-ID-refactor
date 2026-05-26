# Post-Phase 7 Cleanup Owner Evidence Collection

## Status

- status: post_phase7_cleanup_owner_evidence_collection
- bundle type: post_phase7_cleanup_owner_evidence_collection_bundle
- cleanup family: owner_evidence_collection
- no fallback removal
- no production_compat cleanup
- no runtime deletion
- no wildcard cleanup
- no delete_ready=true
- no production behavior change

## Source Blocker Summary

Task-groups blockers from PR #798:

- `/api/admin/automation-conversion/task-groups*` remains blocked for exact-route fallback cleanup.
- `/api/admin/automation-conversion/task-groups*` remains blocked for exact-route production_compat cleanup.
- Missing evidence: route-specific owner approval, latest-main shadow compare, rollback owner, rollback plan, rollback execution evidence, route ownership proof, and production_compat exact-entry cleanup proof.

Workflow-nodes blockers from PR #799:

- `/api/admin/automation-conversion/workflow-nodes*` remains blocked for exact-route fallback cleanup.
- `/api/admin/automation-conversion/workflow-nodes*` remains blocked for exact-route production_compat cleanup.
- Missing evidence: route-specific owner approval, latest-main shadow compare, rollback owner, rollback plan, rollback execution evidence, route ownership proof, and production_compat exact-entry cleanup proof.

Cleanup blocker acceptance from PR #801:

- No fallback removal occurred.
- No production_compat cleanup occurred.
- No runtime deletion occurred.
- `delete_ready` remains false.
- The next safe step is owner evidence collection, not cleanup execution.

## Evidence Collection Matrix

| route_family | cleanup_candidate_id | owner_approval_status | latest_main_shadow_compare_status | rollback_owner_status | rollback_plan_status | rollback_execution_evidence_status | route_ownership_proof_status | production_compat_exact_entry_proof_status | ready_for_fallback_cleanup | ready_for_production_compat_cleanup | blocked_reason | next_owner_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/automation-conversion/task-groups*` | task_groups_exact_route_cleanup | missing | missing | missing | missing | missing | missing | missing | false | false | missing route-specific owner approval, latest-main shadow compare, rollback ownership/plan/execution evidence, route ownership proof, and production_compat exact-entry proof | assign owner, run latest-main shadow compare, attach rollback package, attach manifest proof, and prove exact production_compat entry scope |
| `/api/admin/automation-conversion/workflow-nodes*` | workflow_nodes_exact_route_cleanup | missing | missing | missing | missing | missing | missing | missing | false | false | missing route-specific owner approval, latest-main shadow compare, rollback ownership/plan/execution evidence, route ownership proof, and production_compat exact-entry proof | assign owner, run latest-main shadow compare, attach rollback package, attach manifest proof, and prove exact production_compat entry scope |

## Owner Action Checklist

- Route-specific fallback cleanup approval: owner must approve the exact route family, exact fallback hook, rollback path, and evidence file before any fallback cleanup PR.
- Route-specific production_compat cleanup approval: owner must approve the exact production_compat entry or matcher and confirm no wildcard cleanup is included.
- Latest-main shadow compare: run the route-specific shadow compare from latest `origin/main` and save command, environment, commit SHA, and output as cleanup evidence.
- Rollback owner: assign a named owner responsible for restoring the exact fallback or production_compat route if the canary is reverted.
- Rollback plan: document the restore commit or patch, validation command, expected behavior after rollback, and production communication path.
- Rollback execution evidence: save dry-run or rehearsal output under a route-specific cleanup evidence location before execution.
- Route ownership proof: reference `docs/route_ownership/production_route_ownership_manifest.yaml` and the relevant Phase 6/7 evidence docs for the exact route family.
- production_compat exact-entry proof: prove which exact entry will be cleaned, that no wildcard route is affected, and that rollback can restore the same entry.

## Next Decision Rules

If both route families remain not ready, the next bundle is `post_phase7_cleanup_owner_evidence_waiting_acceptance_bundle`.

If at least one route family becomes ready after owner evidence is supplied, the next bundle is `post_phase7_cleanup_exact_route_retry_bundle`.

This PR does not implement retry, remove fallback, modify production_compat, delete runtime, or set `delete_ready=true`.
