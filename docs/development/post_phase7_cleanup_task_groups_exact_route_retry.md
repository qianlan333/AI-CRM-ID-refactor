# Post-Phase 7 Task-Groups Exact-Route Cleanup Retry

## Status

- status: `post_phase7_cleanup_task_groups_exact_route_retry`
- route family: `/api/admin/automation-conversion/task-groups*`
- fallback removal executed for the selected task-groups exact route: true
- production_compat cleanup executed for the selected task-groups exact route: true
- wildcard cleanup executed: false
- runtime deletion executed: false
- delete_ready: false

## Source PRs

- PR #806: owner evidence waiting acceptance
- PR #811: first task-groups owner evidence validation
- PR #812: task-groups validation blocker acceptance
- PR #813: task-groups shadow compare / rollback evidence
- PR #814: task-groups owner evidence revalidation

## Evidence Used

- owner approval: granted by qianlan
- rollback owner: qianlan
- risk acceptance: cleanup retry allowed only when all evidence is complete
- latest-main shadow compare: passed in PR #813
- rollback rehearsal: passed in PR #813
- route ownership proof: collected in PR #814
- production_compat exact-entry proof: collected in PR #814
- wildcard cleanup required: false

## Cleanup Actions

The retry removes only the selected task-groups production_compat fallback hooks:

- `/api/admin/automation-conversion/task-groups`
- `/api/admin/automation-conversion/task-groups/{path:path}`

The native task-groups GET/POST route remains owned by `aicrm_next.automation_engine`. No workflow-nodes, tasks, workflows, payment, OAuth, WeCom callback, timer, outbound, or public submit route is modified.

## Production Behavior

Production behavior changes only for the selected task-groups exact route family. The route now resolves to the Next-native automation engine owner instead of the selected legacy-forwarding production_compat hooks.

## Fallback Behavior

The selected task-groups legacy fallback hook is removed. This is not broad fallback removal. All unrelated fallback routes remain retained.

## production_compat Behavior

Only the task-groups exact production_compat declarations are removed. No wildcard production_compat route is removed or changed.

## Business Continuity

- selected exact route only: true
- timer execution triggered: false
- outbound send triggered: false
- external live call triggered: false
- high-risk route affected: false
- runtime deletion executed: false
- delete_ready: false

## Risk / Rollback

Rollback is available by reverting this cleanup PR, restoring only the two task-groups production_compat decorators, and rerunning the task-groups checker and focused tests. The prior rollback rehearsal evidence path remains `/tmp/task_groups_rollback_rehearsal_evidence.json`.

## Next Bundle Recommendation

`post_phase7_cleanup_legacy_runtime_recheck_bundle`
