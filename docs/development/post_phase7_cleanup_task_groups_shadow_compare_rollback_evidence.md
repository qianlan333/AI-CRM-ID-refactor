# Post-Phase 7 Task-Groups Shadow Compare / Rollback Evidence

## Status

- status: `post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence`
- route family: `/api/admin/automation-conversion/task-groups*`
- no fallback removal
- no production_compat cleanup
- no runtime deletion
- no wildcard cleanup
- no delete_ready=true
- no production behavior change

## Source State

PR #812 accepted the blocker from task-groups owner evidence validation: owner approval, rollback owner, and risk acceptance were recorded, but latest-main shadow compare and rollback rehearsal had not been truly executed. This bundle fills only those evidence gaps.

## Shadow Compare Evidence

- latest main SHA: `2059090a473ec098acef9237212a40de8bab215f`
- command: `python3 tools/run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py --latest-main-sha 2059090a473ec098acef9237212a40de8bab215f --shadow-output-json /tmp/task_groups_shadow_compare_evidence.json --rollback-output-json /tmp/task_groups_rollback_rehearsal_evidence.json --combined-output-json /tmp/task_groups_shadow_rollback_evidence.json`
- output path: `/tmp/task_groups_shadow_compare_evidence.json`
- executed: true
- passed: true

The compare is default-safe. It reads the route ownership manifest, the production_compat exact route declarations, the native task-groups route declarations, and runs a fixture-only in-memory task-groups probe. It does not connect to production data and does not write production state.

## Rollback Plan

If a later exact-route cleanup retry changes task-groups fallback or production_compat state and must be reverted, rollback is:

1. Revert the cleanup PR or restore the exact route declarations for `/api/admin/automation-conversion/task-groups*`.
2. Restore the route ownership manifest entry to `current_runtime_owner: production_compat`, `production_behavior: legacy_forward`, `legacy_fallback_allowed: true`, and `delete_ready: false`.
3. Rerun the task-groups shadow compare / rollback evidence runner.
4. Rerun the task-groups owner evidence validation checker before any further cleanup.

This bundle does not execute that future cleanup rollback. It rehearses the current rollback posture by confirming the retained fallback and production_compat entries are present and that the rehearsal is a no-op before cleanup.

## Rollback Rehearsal Evidence

- rollback plan path: `docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.md#rollback-plan`
- command: `python3 tools/run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.py --latest-main-sha 2059090a473ec098acef9237212a40de8bab215f --shadow-output-json /tmp/task_groups_shadow_compare_evidence.json --rollback-output-json /tmp/task_groups_rollback_rehearsal_evidence.json --combined-output-json /tmp/task_groups_shadow_rollback_evidence.json`
- output path: `/tmp/task_groups_rollback_rehearsal_evidence.json`
- executed: true
- passed: true
- production behavior changed: false

## Safety Boundaries

- fallback removal executed: false
- production_compat cleanup executed: false
- runtime deletion executed: false
- delete_ready: false
- timer / execution / outbound / payment / OAuth / WeCom callback / public submit: unchanged

## Validation Impact

Because both shadow compare and rollback rehearsal passed, the next safe bundle is:

- `post_phase7_cleanup_task_groups_owner_evidence_validation_bundle`

This PR still does not authorize cleanup retry by itself. It only supplies evidence for the next validation pass.
